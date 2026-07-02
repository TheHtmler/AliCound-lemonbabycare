# PaddleOCR 远程识别服务

开源免费方案：PaddleOCR (PP-OCRv5) + FastAPI + Docker，CPU 推理，适合低并发场景。

## 本地/服务器部署步骤（宝塔面板）

1. **上传代码**：用宝塔「文件管理」把 `paddleocr-service` 整个目录上传到服务器（比如 `/www/wwwroot/paddleocr-service`），或者用 git clone。

2. **准备环境变量**：
   ```
   cd /www/wwwroot/paddleocr-service
   cp .env.example .env
   # 编辑 .env，把 OCR_API_KEY 改成一个长随机字符串
   ```

3. **安装 Docker（如果还没装）**：宝塔面板 -> 软件商店 -> 搜索「Docker 管理器」-> 安装。

4. **构建并启动容器**：
   ```
   docker compose up -d --build
   ```
   首次启动会自动下载 PP-OCRv5 模型文件（几十兆到上百兆，取决于模型），下载完成后会缓存在 `ocr-models` 这个 volume 里，重启容器不会重新下载。

5. **验证服务是否正常**（服务器本机执行）：
   ```
   curl http://127.0.0.1:8501/health
   ```
   返回 `{"status":"ok"}` 说明启动成功。

## 宝塔里配置公网访问（Nginx 反代，当前用 IP，备案通过后换域名）

域名还没备案，暂时用「IP + 端口」的方式绑站点，走 HTTP（没有 HTTPS，Let's Encrypt 不给纯 IP 签证书）。等备案下来了，再把站点域名换成正式域名，重新申请 SSL。

1. 宝塔面板 -> 网站 -> 添加站点，域名那里填服务器公网 IP（比如 `1.2.3.4`），先不用勾 PHP。
2. 站点设置 -> 反向代理 -> 添加反向代理，目标 URL 填 `http://127.0.0.1:8501`。
3. 阿里云安全组 + 宝塔防火墙放开这个站点用的端口（默认 80，如果 80 被占可以用别的端口，比如 `8080`）。
4. （可选）站点设置 -> 配置文件，在 `location /` 里加一行限流，防止被刷：
   ```
   limit_req_zone $binary_remote_addr zone=ocr_limit:10m rate=5r/s;
   limit_req zone=ocr_limit burst=10 nodelay;
   ```

这样对外地址是 `http://<公网IP>:<端口>/ocr/base64`，容器本身只监听 `127.0.0.1`，不会被绕过 Nginx 直接访问。

**注意**：这是明文 HTTP，`X-API-Key` 会裸传输，如果调用方网络环境不可信有被截获的风险。备案通过、换成域名 + HTTPS 之前，尽量把安全组端口限制到已知调用方的 IP。

**备案通过后要做的事**：
1. 宝塔站点设置里把域名从 IP 改成正式域名。
2. 站点设置 -> SSL -> 申请 Let's Encrypt 免费证书，开启强制 HTTPS。
3. 调用方把请求地址从 `http://<公网IP>:<端口>` 换成 `https://ocr.yourdomain.com`。

## 接口说明

鉴权：所有请求都要带 header `X-API-Key: <.env 里配置的 OCR_API_KEY>`。

- `POST /ocr/base64`，body: `{"image_base64": "<图片的 base64 字符串>"}`
- `POST /ocr/file`，multipart 表单，字段名 `file`，直接传图片文件

响应：
```json
{
  "lines": [
    {"text": "识别出的文字", "confidence": 0.98, "box": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]}
  ]
}
```

调用示例：
```
curl -X POST https://ocr.yourdomain.com/ocr/base64 \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d "{\"image_base64\": \"$(base64 -i test.jpg)\"}"
```

## 后续如果并发上来了怎么办

- 先看服务器 CPU 核数，`uvicorn --workers` 可以调大到接近核数（Dockerfile 里改一下 CMD）。
- 单实例撑不住了再考虑加一个 Redis + 任务队列（Celery/RQ）做排队，或者多开几个容器用 Nginx 做负载均衡。目前低并发场景不需要，先别过度设计。
