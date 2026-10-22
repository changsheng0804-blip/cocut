#!/bin/bash
# 路线 B：Gemini（agy）三份考卷并行
export PATH=$HOME/.local/bin:$PATH
cd ~/hark-sandbox-CS/cocut-lab/bench
mkdir -p ../truth && [ -f labels.json ] && mv labels.json ../truth/
COMMON='你是视频审片员。题目在当前目录 questions.json：beats 是每个拍点的设计（what=画面描述，vo=旁白），images 是待审图片，audio 是待审配音。逐项独立判断，不要推断出题规律，不要读当前目录以外的文件。'
IMG='对 images 里 id 以 %s_ 开头的 16 张图，逐张打开看图，对照该 beat 的 what 判断：text=画面里是否有任何可见的字母/单词/文字；swap=是否根本是另一个场景（画的是别的拍的内容）；missing=what 里描述但画面里明显缺失或画错的关键元素（短语列表）；bad=text 或 swap 为真或有明显缺失/画错。只输出一个 JSON 对象写到文件 answers_B_%s.json：{"S1_0a":{"text":false,"swap":false,"missing":[],"bad":false},...}，然后回复"完成"。'
AUD='对 audio 里的 23 条配音逐条听：对 id 以 P 开头的，题目给了 poly（char=要检查的字，pinyin=正确读音），判断 misread=该字是否读错；对 id 以 V_ 开头的，判断 mismatch=音频内容是否不是 text 这句话（配错了别的句子）。只输出一个 JSON 写到文件 answers_B_S3.json：{"P0_ok":{"misread":false},"V_0a":{"mismatch":false},...}，然后回复"完成"。'
run() { local s=$(date +%s); agy --model gemini-4-argon-high --dangerously-skip-permissions -p "$COMMON $1" > log_B_$2.txt 2>&1; echo "$2 $(( $(date +%s) - s ))" >> timing_B.txt; }
rm -f timing_B.txt answers_B_*.json
run "$(printf "$IMG" S1 S1)" S1 &
run "$(printf "$IMG" S2 S2)" S2 &
run "$AUD" S3 &
wait; cat timing_B.txt; ls answers_B_*.json; tail -3 log_B_*.txt
