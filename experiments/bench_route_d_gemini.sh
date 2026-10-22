#!/bin/bash
# 路线 D 的复核端用 Gemini：只答 questions_D.json 里点名的问题（需在桌面会话/screen 里跑）
export PATH=$HOME/.local/bin:$PATH
cd ~/hark-sandbox-CS/cocut-lab/bench
P='你是审片复核员。打开当前目录 questions_D.json。对 images 里每一项，打开它的图片，按 asks 顺序逐题只回答 yes、no 或 unsure，只看点名的这一处，不评价别的，不读当前目录以外的文件。'
PI="$P 只做 images 部分。输出一个 JSON 写到 answers_D_gemini_img.json：{\"S1_0a\":{\"0\":\"yes\",\"1\":\"no\"},...}（键是 asks 下标），然后回复\"完成\"。"
PA='你是配音校对员。打开当前目录 questions_D.json，只做 audio 部分：逐条听音频，回答 asks 的问题，只答 yes、no 或 unsure。输出 JSON 写到 answers_D_gemini_aud.json：{"V_1a":{"0":"no"},...}，然后回复"完成"。'
run() { local s=$(date +%s); agy --model gemini-4-argon-high --dangerously-skip-permissions -p "$1" > log_D_$2.txt 2>&1; echo "$2 $(( $(date +%s) - s ))" >> timing_D.txt; }
rm -f timing_D.txt answers_D_gemini_*.json
run "$PI" img & run "$PA" aud & wait
cat timing_D.txt; ls answers_D_gemini_*.json
