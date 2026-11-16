# HISTORY

## 沿革

### Origin

This doctrine originated in `royalskynet/coding-hermes`, a fork of `NousResearch/hermes-agent`.

最初位置：`skills/software-development/coding-hermes/SKILL.md`，由 commit `4a679a3296367f69ec7dca150a904a1638178b19`（2026-08-20T17:31:13Z，author royalskynet）引入，走 PR [#6](https://github.com/royalskynet/coding-hermes/pull/6)，分支 `feat/coding-hermes-skill`。

### Extraction

The doctrine was extracted into this standalone skill because:

1. The content is decoupled from the hermes-agent runtime (doc-only discipline).
2. Bundled inside a 9000+ file fork, it cannot be independently installed.
3. The fork's CI is independently red (drift vs upstream: ruff enforcement, Windows footguns, test slices 1,3,4 on `main`), so docs-only PRs get caught in the crossfire.

### mdispatch removal

Early versions of this doctrine depended on `royalskynet/mdispatch` (plan.md dispatch CLI with falsifiability lint). That repo no longer exists (GitHub API returns 404). The dependency entry and `curl | sudo tee` install line were removed in coding-hermes's `chore/drop-mdispatch-dead-dep` PR. Dispatch flow is now handled by each harness's own kanban mechanism.

### Preserved dependency

`royalskynet/fixindex` remains in maintenance (last update 2026-08-18) and is the optional dependency of this skill.

---

## 沿革

### 來源

本紀律誕生於 `royalskynet/coding-hermes`，該 repo 是 `NousResearch/hermes-agent` 的 fork。

原始位置：`skills/software-development/coding-hermes/SKILL.md`，由 commit `4a679a3296367f69ec7dca150a904a1638178b19`（2026-08-20T17:31:13Z，author royalskynet）引入，走 PR [#6](https://github.com/royalskynet/coding-hermes/pull/6)，分支 `feat/coding-hermes-skill`。

### 抽出原因

紀律內容與 hermes-agent runtime 無耦合（純文檔紀律），綁在 9000+ 檔的 fork 內無法被單獨安裝；且該 fork 的 CI 相對 upstream 已漂移（ruff / Windows footguns / test slices 1,3,4 在 `main` 即為紅），docs-only PR 也被連坐。

### mdispatch 廢除

早期紀律曾依賴 `royalskynet/mdispatch`（plan.md 派工 CLI，含 falsifiability lint）。該 repo 已不存在（GitHub API 404），相關 README 條目與 `curl | sudo tee` 安裝指令於本次一併移除（見 coding-hermes 的 `chore/drop-mdispatch-dead-dep` PR）。派工流程改由各 harness 自己的工單檢查機制承接。

### 保留依賴

`royalskynet/fixindex` 仍在維護（最後更新 2026-08-18），為本 skill 的選用依賴。

## 2026-09-14 v2.2.0 本體瘦身拆 references

本體 16KB→≤7KB，細節拆六份 `references/`，progressive disclosure。行為不變，僅搬移與新增 References 索引。

## 2026-09-26 v2.3.0 自動情境路由

SKILL.md 改為六模式路由表（定向／圖譜優先／結構映射／查證／審計／專案記憶），先選最輕且足夠的模式、證據不足才升級。新增 references/orientation-routing.md 完整定義升降級判準、圖譜新鮮度與審計輸出；research-playbook、fixindex-usage、command-construction 同步小修。

## 2026-10-01 v2.4.0 Layer 2 抽出成 wheel skill

Layer 2 找輪子與查證抽成獨立 `skills/wheel/`（三軸＋深度分級＋授權/活躍檢查＋7 級裁決＋不對稱閘＋registry），概念取自 deja-vu 與 dont-reinvent。coding-hermes 只留指標，刪除 references/research-playbook.md。同一份 wheel 當時也複製進 royalskynet/genie-harness 取代 genie-research（2026-10-18 起改為本 repo 的映射，不再留副本）。

## 2026-10-18 v3.0.0 只留 wheel；coding-hermes 獨立成 ether-code；併入 0.4.9

本 repo 的角色收斂為「只放 wheel」。三件事在同一天完成：

1. **只留 wheel。** `coding-hermes` 從本 repo 移除，獨立成 [royalskynet/ether-code](https://github.com/royalskynet/ether-code)；`commands/dispatch.md` 移為 ether-code 的 `skills/coding-hermes/references/dispatch.md`（仍可複製成 `~/.claude/commands/dispatch.md`）。
2. **併入 genie-harness 版的差異（含 0.4.9）。** 先前 genie-harness 有一份更完整的 wheel；0.4.9 又加了社群軸不限 closed、讀留言與關閉原因、查未合 PR、社群計票、除錯題先驗元件歸屬，同批併入；更早加入的 host 專屬 registry CLI、HN／Stack Overflow／deps.dev 降級鏈、Standard 起社群軸至少兩個來源、採用量欄、`review_by` 30／90／180 天也在其中。這些通用化後併入本 repo；registry CLI 落在 `skills/wheel/scripts/wheel_registry.py`（只依賴標準庫），SKILL.md 保留 `grep`／`printf` 等價退回寫法，並由 `scripts/test_skill.py` 執行原文驗證兩者一致。
3. **新增逆向能力。** `/wheel` 明定預設同時做三件事：決策（社群智慧＋官方文檔）、輪子（成熟方案清單）、逆向（閉源產物反推；情境需要或使用者要求才跑）。逆向只到事實與清單（asar、包成員、`otool -L`、`codesign -dv`、strings、sourcemap），借鏡 [rea](https://github.com/royalskynet/rea) 的「依目標路由、先報觀察再推斷、unknown ≠ absence」骨架，不含其 provider 抽象與深層反編譯。

本機收斂：`~/.claude/skills/wheel` 維持指向 `~/.agents/skills/wheel`（genie-harness 安裝的 symlink），`~/.agents/skills/wheel` 改為直接指向本 repo；舊的三份 `coding-hermes` 副本（`~/.agents`、`~/.codex`、`Ether-claude`）刪除，統一指向 `~/dev/ether-code`。


## 2026-11-16 社群軸改由腳本執行並留收據

稽核本機 session 記錄：用過 wheel 的 9 個 session 有 6 個沒送出任何社群查詢，其中 5 個照樣登記了輪子卡。「Standard 起至少兩個來源」只寫在文字裡，登記端不驗。

1. **`scripts/wheel_community.py`。** 一次並行查 GitHub issues／PRs／Discussions、Hacker News、Stack Overflow、Reddit，每個來源回報狀態，「有回應」（`ok`／`no-results`）與「沒回應」（限流、被擋、連不上、略過）分開。查詢送出前去掉家目錄、登入名、信箱、長 hex。每次執行在 `~/.wheel/ledger.jsonl` 留一筆收據。
2. **登記閘。** `wheel_registry.py add` 要有 120 分鐘內、未被別張卡用過的收據，否則 exit 2；Quick 用 `add --quick`，裁決只有 不做／換題 免查。新增 `audit` 子指令統計歷來登記的查證狀況。
3. **除錯題自動走 fix。** 題目本身是錯誤訊息或故障症狀就照 `references/fix.md` 跑，不必明打 `/wheel fix`。
4. **`references/community.md`。** 狀態讀法、換視角、追一層、查反證、停止條件。做法借鏡 mvanhorn/last30days-skill、affaan-m/ECC search-first、Emanuelel/dont-reinvent、iagochavarry/who-built-this-before-me、rianczerwinski/prior-art-skill。
5. **Windows。** CLI 輸出固定 UTF-8；測試把 `USERPROFILE` 一併導向暫存目錄（原本會寫進真實登記簿）、bash 由 PATH 解析（原本會跑到 WSL）、補 `LANG`（Git Bash 的 `grep -i` 在沒有 locale 時會 abort）。
