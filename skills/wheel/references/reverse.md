# 閉源軸（逆向）

只在答案取決於一個**看不到源碼**的產物時跑：競品 Electron app、APK、binary、私有 registry 的套件。

先分流：其實有公開源碼或 sourcemap → 回三軸讀原始碼。只想知道對方用了哪些輪子 → 依賴清單就夠，不下到符號層。

| 目標 | 指令（只讀，輸出行數或前 N 筆） |
|---|---|
| Electron | `npx asar list <app>/resources/app.asar`；`npx asar extract-file` 取 `package.json` 看依賴 |
| 包／APK／IPA／MSIX／DMG | `unzip -l`／`tar -tf` 列成員；APK 另看 `META-INF`、`lib/*/`、`AndroidManifest.xml` |
| macOS binary／app | `otool -L`（動態庫）、`codesign -dv --verbose=4`（簽名與 team ID）、`strings -a \| grep -iE 'version\|license\|copyright'` |
| 網頁 | 先 `camofox_fetch`／WebFetch 取頁，再拉 `*.map` sourcemap 還原模組 |

邊界：只碰自己擁有或有權檢視的產物；只取事實與清單，不整份反編譯成可用源碼、不碰 DRM／繞過。Ghidra／IDA 級深層反編譯不在本 skill 範圍。

產物揭露的輪子回 SKILL.md §5 重新裁決，不另立裁決詞；產物的授權同樣套 §4。輪子卡前多一行：
`閉源：<產物>｜觀察到：<依賴或設計>｜推斷：<一句>｜未覆蓋：<未知>`
