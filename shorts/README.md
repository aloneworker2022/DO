# NAS Shorts 📱

把 Synology NAS 裡的影片變成「抖音 / Reels」那樣，全螢幕、上下一直滑的瀏覽方式。

- 上滑下一部、下滑上一部，自動播放、循環播放
- 隨機 / 最新 / 最舊排序，可依資料夾篩選
- 點畫面暫停、點底部進度條跳轉、右側開關聲音與下載
- 電腦上可用 ↑ ↓（或 j / k）切換、空白鍵暫停、m 靜音
- 自動略過 Synology 的 `@eaDir`、`#recycle` 等系統資料夾
- 支援 HTTP Range，拖曳進度、iPhone Safari 都能順暢播放
- 只用 Python 標準函式庫，DS723+ 上跑起來幾乎不吃資源

## 在 DS723+ 上安裝（Container Manager）

1. 套件中心安裝 **Container Manager**。
2. 把這個 `shorts` 資料夾複製到 NAS，例如 `/volume1/docker/nas-shorts`。
3. 編輯 `docker-compose.yml`，把 `/volume1/video` 改成你放影片的資料夾。
   - 想看多個資料夾，可以多掛幾行，例如
     `- /volume1/photo/手機影片:/videos/手機:ro`
4. Container Manager →「專案」→「新增」→ 路徑選剛才的資料夾 → 會自動讀到 `docker-compose.yml` → 建置並啟動。
5. 手機瀏覽器打開 `http://NAS的IP:8090`。
   - iPhone：Safari「分享」→「加入主畫面」，就會像 App 一樣全螢幕開啟。

不想用 Docker 也可以：DSM 上只要有 Python 3，直接
`VIDEO_DIR=/volume1/video PORT=8090 python3 server.py`。

## 設定

| 環境變數 | 預設 | 說明 |
| --- | --- | --- |
| `VIDEO_DIR` | `/videos` | 要掃描的影片資料夾（含子資料夾） |
| `PORT` | `8080` | 容器內的埠號 |
| `AUTH_USER` / `AUTH_PASS` | 空 | 設定後需要帳密才能看 |

影片清單每 60 秒重新掃描一次，新放進去的影片稍等一下重新整理就會出現。

## 注意事項

- **格式**：瀏覽器能直接播的才行，建議 H.264 的 `.mp4`。iPhone 拍的 HEVC `.mov` 在 iPhone / Mac Safari 可播，但 Android Chrome 或 Windows 可能不行。
  這個工具不做轉檔（DS723+ 沒有內顯，即時轉檔很吃 CPU）；需要的話可先用 ffmpeg 轉成 H.264 mp4。
- **外網存取**：預設只建議在家裡區網用。要從外面看，請設定 `AUTH_USER` / `AUTH_PASS`，
  並透過 DSM「控制台 → 登入入口網站 → 進階 → 反向代理伺服器」加上 HTTPS，不要直接把埠號開到外網。
