# NAS Shorts 📱

把 Synology NAS 裡的影片變成「抖音 / Reels」那樣，全螢幕、上下一直滑的瀏覽方式。

- 上滑下一部、下滑上一部，自動播放、循環播放
- **往右滑喜歡（❤️ +1）、往左滑不喜歡（❤️ −1）**，然後自動跳下一部；同一部影片每天只能評一次（以手機日期為準）
- 右上角顯示目前影片的愛心數，今天評過的會變紅色
- 右上角 ☰ 設定：選播放順序（隨機 / 最新 / 最舊 / 最受歡迎 / 最不受歡迎），直接在網頁上瀏覽並選擇要播放的資料夾（設定存在 NAS 上，每台裝置共用）
- 點畫面暫停、點底部進度條跳轉、右側開關聲音與下載
- 電腦上可用 ↑ ↓（或 j / k）切換、← → 評分、空白鍵暫停、m 靜音
- 自動略過 Synology 的 `@eaDir`、`#recycle` 等系統資料夾
- 支援 HTTP Range，拖曳進度、iPhone Safari 都能順暢播放
- 只用 Python 標準函式庫，DS723+ 上跑起來幾乎不吃資源

## 推薦：自動更新版（不用上傳檔案）

1. Container Manager →「專案」→「新增」，路徑選一個空資料夾（例如 `docker/nas-shorts`），
   來源選「建立 docker-compose.yml」。
2. 把 [`docker-compose.nas.yml`](docker-compose.nas.yml) 的內容整份貼上。
3. 完成後打開 `http://NAS的IP:8090`，點右上角 ☰ 選擇要播放的資料夾，按「儲存」。

每次容器啟動都會從 GitHub 抓最新版，**要更新只要在專案上按「重新啟動」**。
抓不到（例如 NAS 暫時沒網路）時會繼續用上次下載的版本。

## 在 DS723+ 上安裝（Container Manager，手動上傳檔案）

1. 套件中心安裝 **Container Manager**。
2. 把這個 `shorts` 資料夾複製到 NAS，例如 `/volume1/docker/nas-shorts`。
3. `docker-compose.yml` 預設把整個 `/volume1` 唯讀掛進去，之後在網頁右上角 ☰ 選資料夾即可。
   - 不想讓網頁看到整個 volume1 的資料夾名稱，可以改成只掛特定共用資料夾，例如
     `- /volume1/video:/videos/video:ro`、`- /volume1/photo:/videos/photo:ro`
4. Container Manager →「專案」→「新增」→ 路徑選剛才的資料夾 → 會自動讀到 `docker-compose.yml` → 建置並啟動。
5. 手機瀏覽器打開 `http://NAS的IP:8090`。
   - iPhone：Safari「分享」→「加入主畫面」，就會像 App 一樣全螢幕開啟。

不想用 Docker 也可以：DSM 上只要有 Python 3，直接
`VIDEO_DIR=/volume1 SETTINGS_FILE=./config/settings.json LIKES_FILE=./config/likes.json PORT=8090 python3 server.py`。

## 設定

| 環境變數 | 預設 | 說明 |
| --- | --- | --- |
| `VIDEO_DIR` | `/videos` | 根目錄，設定頁只能選這底下的資料夾 |
| `SETTINGS_FILE` | `/config/settings.json` | 選好的資料夾存在這裡 |
| `LIKES_FILE` | `/config/likes.json` | 每部影片的愛心數存在這裡 |
| `PORT` | `8080` | 容器內的埠號 |
| `AUTH_USER` / `AUTH_PASS` | 空 | 設定後需要帳密才能看 |

播放順序「最受歡迎」從愛心最多的開始播，只播愛心 ≥ 0 的；「最不受歡迎」從愛心最少的開始播，只播愛心 ≤ 0 的。
愛心數相同的影片會隨機排列。

影片清單每 60 秒重新掃描一次，新放進去的影片稍等一下重新整理就會出現。

## 注意事項

- **格式**：瀏覽器能直接播的才行，建議 H.264 的 `.mp4`。iPhone 拍的 HEVC `.mov` 在 iPhone / Mac Safari 可播，但 Android Chrome 或 Windows 可能不行。
  這個工具不做轉檔（DS723+ 沒有內顯，即時轉檔很吃 CPU）；需要的話可先用 ffmpeg 轉成 H.264 mp4。
- **外網存取**：預設只建議在家裡區網用。要從外面看，請設定 `AUTH_USER` / `AUTH_PASS`，
  並透過 DSM「控制台 → 登入入口網站 → 進階 → 反向代理伺服器」加上 HTTPS，不要直接把埠號開到外網。
