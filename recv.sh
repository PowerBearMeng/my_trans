#!/bin/bash

# CoDel 配置 - 为激光雷达优化
# target=100ms: 目标排队延迟 100ms（约 1 帧的时间）
# interval=1000ms: 1秒评估窗口（10帧的时间）
mm-link ~/driving/data/trace_data/1103/trace/2_1.trace \
        ~/driving/data/trace_data/1103/trace/2_1.trace \
        --downlink-queue=codel \
        --downlink-queue-args="target=100,interval=1000,packets=2000" \
        -- bash -c "cd ~/driving/my_trans/gstream && /bin/python3 main_receive.py"

# 说明：
# - target=100ms = 1帧时间，保证低延迟
# - 当排队延迟超过 100ms 时，CoDel 会主动丢包
# - 比固定队列大小更智能