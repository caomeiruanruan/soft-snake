# 把这条蛇搬到 Render（10 分钟，全点点点）

## 为什么要搬

现在蛇跑在镇江这台电脑上，中间隔着 Cloudflare 隧道。
官方竞技场在美西，每一步要：

    美西机房 → Cloudflare 边缘 → 镇江 → 原路返回

实测 **493ms**，上限 **500ms**。等于每步都在悬崖边上，偶尔超时就直接判负。
同场对手是 **29ms / 79ms**。

搬到 Render（俄勒冈机房）之后，延迟大约 **20–40ms**。

---

## 第一步：把这三个文件传上 GitHub

需要的文件（都在 `E:\workspaceformylove\snake\`）：

```
server.py          ← 蛇本体
core.py            ← 脑子
requirements.txt   ← 空的（只用标准库）
render.yaml        ← Render 的部署说明书
```

做法二选一：

- **A（会命令行）**：新建一个仓库，把上面四个文件推进去
- **B（不想碰命令行）**：GitHub 网页 → New repository → 命名 `soft-snake` → Create
  → 页面上点 `uploading an existing file` → 把这四个文件拖进去 → Commit

---

## 第二步：注册 Render

1. 打开 https://render.com
2. 点 **Get Started** → 选 **GitHub** 登录（你那个号今天刚解封）
3. 授权它读你的仓库（只需要读权限）

---

## 第三步：新建服务

1. 右上 **New** → **Blueprint**
2. 选刚才那个 `soft-snake` 仓库
3. Render 会自动读到 `render.yaml`，显示一个叫 `soft-snake` 的服务
4. 点 **Apply** / **Create**
5. 等 1–2 分钟，状态从 `Building` 变 `Live`

---

## 第四步：拿到地址

服务页面上会显示一个网址，长这样：

```
https://soft-snake-xxxx.onrender.com
```

点开它，应该看到：

```json
{"apiversion": "1", "author": "soft", "color": "#7C9CF5", ...}
```

**看到这行字就成功了。**

---

## 第五步：换地址

回到 Battlesnake 的蛇的设置页，把 URL 从原来那个 `trycloudflare.com` 的
换成新的 `onrender.com` 地址，保存。

然后再开一局，看回放里的 Latency。

---

## 注意

- **免费档会休眠**：15 分钟没人访问就睡，醒来要 30–50 秒。
  打排位之前，先自己开一局把它叫醒，否则第一局必超时。
- 所以：**打之前先访问一次那个网址**，看到 JSON 再开局。
- 本地这套不用删，随时可以切回来跑。
