# scholarflow 专属部署终版（Windows Server 2022 + Docker）

> 服务器：阿里云 ECS 华东1（杭州）`i-bp11wmt3hdusz4nlks4v`
> 系统：Windows Server 2022 数据中心版 64位中文版，2核 vCPU / 2 GiB / ESSD Entry 40 GiB
> 公网 IP：`121.196.233.81`（峰值带宽 100 Mbps，按流量计费）
> 域名：`ai.luoguanggu777.xyz`（子域名，DNS 托管在 Cloudflare，老服务器同款链路）
> 踩坑记录（老服务器）：/api/docs 502、SQLite 配置报错、问答失败——本文已内置对应预防措施，见「老坑预防」章节
> 策略：**从零开始**（老服务器数据无备份，不迁移），后端全家桶走 Docker，前端 dist + Nginx

---

## 总体架构

```
浏览器 → Cloudflare DNS(A: 121.196.233.81) → 服务器
  → Nginx(Windows, :80)
      ├─ /          → C:\scholarflow\vue-frontend\dist (静态)
      └─ /api/      → 127.0.0.1:8000 (WSL2 内 Docker 容器)
  → Docker(WSL2 Ubuntu 内)
      ├─ api      (FastAPI, 8000)
      ├─ mysql    (3306, 仅内网)
      └─ redis    (6379, 仅内网)
```

> ⚠️ Windows Server 2022 **不能装 Docker Desktop**（它只支持 Win10/11 客户端版）。服务器上的正确姿势是 **WSL2 + Ubuntu + Docker CE**，全程命令行，稳定性反而更好。

---

## 第 0 步：安全组（阿里云控制台）

ECS → 安全组 → 配置规则 → 入方向添加：

| 协议 | 端口 | 授权对象 | 说明 |
|------|------|----------|------|
| TCP | 80 | 0.0.0.0/0 | HTTP（备案后开放给公网；备案前建议只填你本地 IP） |
| TCP | 443 | 0.0.0.0/0 | HTTPS（同上） |
| TCP | 3389 | 你的本地IP/32 | RDP 远程桌面（**不要对全网开放**） |

MySQL(3306)、Redis(6379)、后端(8000) 一律不开公网。

---

## 第 1 步：远程连接并准备目录

本地 PowerShell：

```powershell
mstsc /v:121.196.233.81
```

（若密码没设过：控制台 → 实例 → 重置密码 → 重启生效）

服务器上（管理员 PowerShell）：

```powershell
mkdir C:\scholarflow
```

---

## 第 2 步：安装 WSL2 + Ubuntu（服务器上的 Docker 底座）

管理员 PowerShell：

```powershell
# 启用所需功能
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 设置虚拟内存页面文件（2G 内存机器必做，否则构建时 OOM）
wmic computersystem set AutomaticManagedPagefile=False
wmic pagefileset where name="C:\\pagefile.sys" set InitialSize=4096,MaximumSize=8192

# 重启
shutdown /r /t 5
```

重启后，下载并安装 WSL2 内核包（PowerShell）：

```powershell
Invoke-WebRequest -Uri https://wslstorage.blob.core.windows.net/wslblob/wsl_update_x64.msi -OutFile $env:TEMP\wsl_update.msi
msiexec /i $env:TEMP\wsl_update.msi /qn
wsl --set-default-version 2
wsl --install -d Ubuntu-22.04
```

> 如果 `wsl --install` 拉取慢/失败，备选：下载 Ubuntu 22.04 WSL 镜像离线导入：
> `Invoke-WebRequest https://aka.ms/wslubuntu2204 -OutFile C:\ubuntu.appx`，然后
> `Add-AppxPackage C:\ubuntu.appx`，再运行 `ubuntu2204.exe`。

首次进入 Ubuntu 会让你建 Linux 用户（如 `deploy`）+ 密码，记住它。

**2G 内存限制（重要）**：给 WSL2 限内存，防止把 Windows 挤爆。Windows 侧创建 `C:\Users\Administrator\.wslconfig`：

```ini
[wsl2]
memory=1536MB
swap=4GB
processors=2
```

---

## 第 3 步：WSL2 Ubuntu 内安装 Docker CE

进入 Ubuntu（PowerShell 输入 `wsl -d Ubuntu-22.04`），执行：

```bash
# 国内源安装 Docker CE
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://mirrors.aliyun.com/docker-ce/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 当前用户免 sudo（执行后重开一次终端生效）
sudo usermod -aG docker $USER

# 开机自启（WSL 内用 service）
sudo service docker start

# 配置镜像加速
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://docker.1ms.run"],
  "log-driver": "json-file",
  "log-opts": {"max-size": "30m", "max-file": "3"}
}
EOF
sudo service docker restart

# 验证
docker --version && docker compose version
docker run --rm hello-world
```

> **WSL 开机自启 Docker**：Windows 侧建任务计划程序（开机/登录时运行）：
> `wsl -d Ubuntu-22.04 -u root -- service docker start`

---

## 第 4 步：把代码弄进 WSL

推荐 Git（最干净）。先在服务器 Ubuntu 内：

```bash
sudo apt-get install -y git
cd ~
git clone <你的仓库地址> scholarflow
```

> 项目还没推到远程仓库的话，本地 Windows 上先 `git push`。当前本地有一批未跟踪文件（docs/、BACKLOG.md 等），部署只需要已提交的代码，不影响。
>
> 备选（不走 Git）：本地 Windows 打包后 scp 到 Windows 侧 C:\scholarflow，WSL 里可直接访问 `/mnt/c/scholarflow`，但 IO 慢，建议复制进 Linux 文件系统：
> `cp -r /mnt/c/scholarflow ~/scholarflow`

---

## 第 5 步：配置生产环境变量

```bash
cd ~/scholarflow
cp .env.production.example .env.production
nano .env.production
```

**必改项**：

```
DASHSCOPE_API_KEY=你自己的百炼Key（必改！）
```

其余保持模板值即可：`DATABASE_URL` 指向 `mysql:3306`、`REDIS_URL` 指向 `redis:6379/0`、`API_BASE_URL=http://api:8000`、`QDRANT_PATH=/app/data/qdrant_local`。

**生产加固（顺手做掉）**：编辑 `docker-compose.yml`，
1. 删掉 `mysql` 服务的 `ports: "3307:3306"` 和 `redis` 服务的 `ports: "6379:6379"`（不暴露到宿主机）；
2. 把 `MYSQL_ROOT_PASSWORD` / `MYSQL_PASSWORD` 改成强口令，并同步改 `.env.production` 里 `DATABASE_URL` 的密码；
3. `api` 服务保留 `ports: "8000:8000"`（Nginx 反代需要，只监听宿主即可，安全组不开公网）。

**2G 内存专项**：mysql 服务 command 里追加参数限制内存：

```yaml
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --innodb-buffer-pool-size=256M
      - --performance-schema=OFF
```

---

## 第 6 步：构建并启动

```bash
cd ~/scholarflow
docker compose up -d --build
docker compose ps
docker compose logs -f api   # 看到 Uvicorn running 即成功，Ctrl+C 退出日志
```

首次构建要装 Python 依赖，预计 5~15 分钟（取决于网络）。若 `docker.1ms.run` 拉不动基础镜像，改用：
`docker pull python:3.11-slim` 直连，或在 daemon.json 里换其它镜像站。

## 第 7 步：初始化数据库

```bash
docker compose exec api python scripts/init_mysql_schema.py
curl http://127.0.0.1:8000/health/ready   # 在 WSL 内自测
```

---

## 第 8 步：前端构建

WSL Ubuntu 内：

```bash
sudo apt-get install -y nodejs npm   # 若版本过旧，用 nvm 装 Node 18/20
cd ~/scholarflow/vue-frontend
npm config set registry https://registry.npmmirror.com
npm install
npm run build    # 产物在 dist/
```

> 2G 内存机器上 `npm run build` 可能吃紧，构建前关掉不必要的进程；实在不行在**本地 Windows** 构建好 dist 再传上去（前端构建产物与运行环境无关，这是完全可行的降级方案）。

---

## 第 9 步：Windows 侧安装 Nginx

回到服务器 Windows（管理员 PowerShell）：

```powershell
# 下载 nginx for Windows
Invoke-WebRequest http://nginx.org/download/nginx-1.26.2.zip -OutFile C:\nginx.zip
Expand-Archive C:\nginx.zip C:\
Rename-Item C:\nginx-1.26.2 C:\nginx
```

前端产物从 WSL 拷到 Windows：

```powershell
wsl -d Ubuntu-22.04 -- bash -c "cp -r ~/scholarflow/vue-frontend/dist /mnt/c/nginx/html/scholarflow"
```

写配置 `C:\nginx\conf\conf.d\scholarflow.conf`（先在 `nginx.conf` 的 http{} 里加一行 `include conf.d/*.conf;`）：

```nginx
server {
    listen 80;
    server_name ai.luoguanggu777.xyz 121.196.233.81;

    root C:/nginx/html/scholarflow;
    index index.html;
    client_max_body_size 50m;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

> 注意：WSL2 的端口会自动转发到 Windows 宿主机（localhost:8000 即可访问容器），所以这里 `127.0.0.1:8000` 成立。若个别版本不转发，在 Windows 执行：
> `netsh interface portproxy add v4tov4 listenport=8000 connectaddress=(wsl hostname -I)`（用 WSL 的 IP）。

启动 Nginx 并设开机自启（任务计划程序，或用 `nssm install nginx C:\nginx\nginx.exe` 注册系统服务，推荐 nssm）：

```powershell
C:\nginx\nginx.exe
```

**Windows 防火墙放行 80**：

```powershell
New-NetFirewallRule -DisplayName "HTTP 80" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
New-NetFirewallRule -DisplayName "HTTPS 443" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

---

## 第 10 步：Cloudflare 切解析

CF 面板 → DNS → Records：

| 类型 | 名称 | 内容 | 代理 |
|------|------|------|------|
| A | `ai` | `121.196.233.81` | 先 DNS only（灰云） |

> 若同时想用裸域跳转，可另加 `@` A 记录 + CF 的「重定向规则」把 `luoguanggu777.xyz` 301 到 `ai.luoguanggu777.xyz`，主站用子域即可。

> ⚠️ 服务器在杭州（大陆），**域名要能通过 80/443 正式对外服务，必须先完成 ICP 备案**。未备案期间：
> - 用 `http://121.196.233.81` 或非 80 端口（如 8080，需同步改 nginx listen 和安全组）自测，不受拦截；
> - 不要开 CF 橙云代理来"绕"备案——回源大陆机器同样会被拦，且可能触发阿里云封 80 端口。
> 备案入口：阿里云 App → 备案（`.xyz` 后缀可备案，周期约 1~2 周）。

---

## 第 11 步：验证清单

- [ ] WSL 内 `curl 127.0.0.1:8000/health/ready` 返回正常
- [ ] Windows 内浏览器开 `http://121.196.233.81` 见到登录页
- [ ] 注册账号 → 建课程 → 上传 PDF → RAG 问答全流程通
- [ ] CF 解析生效后 `http://luoguanggu777.xyz` 同样可访问（备案通过后）
- [ ] 重启服务器一次，验证 Docker 容器（restart: unless-stopped）和 Nginx 都自动起来

---

## 日常运维速查

```bash
# WSL 内
cd ~/scholarflow
docker compose ps               # 状态
docker compose logs -f api      # 后端日志
docker compose up -d --build    # 更新代码后重建
docker compose exec api python scripts/backup_data.py   # 备份
```

```powershell
# Windows 侧
C:\nginx\nginx.exe -s reload    # 改配置后重载
wsl --shutdown                  # 彻底重启 WSL（出怪问题时）
```

## 常见坑（2核2G 专属）

| 现象 | 处置 |
|------|------|
| 构建时 WSL 被 OOM 杀掉 | `.wslconfig` 增大 swap；前端改在本地构建再传 dist |
| api 容器反复重启 | `docker compose logs api`，九成是 Key 无效或 MySQL 未就绪 |
| Windows 访问不了 8000 | WSL 端口未转发，用 netsh portproxy 兜底（见第 9 步） |
| 服务器重启后服务没起来 | 检查任务计划：wsl docker start + nssm nginx |
| 磁盘涨 | `docker system prune -f` 清理；日志已限 30m×3 |
| 按量计费心疼 | 不用时控制台「停机」（保留 ESSD 盘费用）；注意按量实例别开自动释放 |

---

## 老坑预防（上一台服务器踩过的三个坑）

### 坑 1：`/api/docs` 返回 502

根因通常是：Nginx 起了、但 FastAPI 没就绪（构建后容器崩溃/重启中），或代理指向的后端地址不通。本次预防与排查顺序：

1. 先分层确认——WSL 内 `curl http://127.0.0.1:8000/health`，再 Windows 侧浏览器开 `http://127.0.0.1:8000/health`，最后才查 Nginx。哪层不通修哪层。
2. `docker compose ps` 看 api 是否 `running (healthy)`；`docker compose logs api` 看崩溃原因。
3. 确认 Nginx `proxy_pass http://127.0.0.1:8000/;` 末尾斜杠存在——`/api/docs` 会被正确转成后端 `/docs`。
4. WSL2 端口未转发到 Windows 宿主机时（浏览器 502 但 WSL 内 curl 正常），用第 9 步的 `netsh portproxy` 兜底。

### 坑 2：SQLite 配置报错

根因通常是：`.env.production` 漏配或路径指向了容器内不存在的目录（如沿用了本地开发的相对路径 `./data/...`，容器内工作目录变化导致找不到/没权限）。本次预防：

1. `.env.production` 必须用**容器内绝对路径**（模板已是）：`VECTOR_DB_DIR=/app/data/chroma`、`CHECKPOINT_DB_PATH=/app/data/memory/checkpoints.sqlite`、`AUTH_DB_PATH=/app/data/auth/auth.sqlite`、`QDRANT_PATH=/app/data/qdrant_local`。
2. 确认 `docker-compose.yml` 里 api 服务挂载了 `./data:/app/data`（宿主机 `~/scholarflow/data` 会持久化，容器重启不丢）。
3. 首次启动前建目录：`mkdir -p data/chroma data/memory data/auth data/qdrant_local`。
4. 权限问题（容器内报 readonly / permission denied）：`sudo chown -R 10001:10001 data`（Dockerfile 里用的是 uid 10001 的 scholarflow 用户）。

### 坑 3：问答失败

问答链路 = 后端 → DashScope（embedding/rerank/chat）→ Qdrant 检索。逐项排查：

1. **Key 无效/欠费**（最常见）：`docker compose exec api python scripts/check_model.py` 或直接看 `logs/` 里是否 401/403/额度报错；确认 Key 有百炼的 embedding(text-embedding-v3) + rerank(gte-rerank-v2) + chat(qwen-plus) 三类权限。
2. **知识库为空**：老数据没迁移，新库必须先建课程 → 上传资料 → 等入库任务完成，再问答；没有任何 chunk 时问答必然无引用甚至失败。
3. **超时**：`CHAT_TIMEOUT_SECONDS=60`、Nginx `proxy_read_timeout 300s` 已放宽；若仍超时看是模型慢还是检索挂了（`logs/` 里看卡在哪一步）。
4. **Redis 连不上**：问答带限流/缓存，Redis 挂了会连带失败；`docker compose ps` 确认 redis healthy，`.env.production` 的 `REDIS_URL=redis://redis:6379/0`。

