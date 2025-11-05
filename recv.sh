#!/bin/bash

mm-link ~/driving/data/trace_data/1103/trace/6_2.trace \
        ~/driving/data/trace_data/1103/trace/6_2.trace \
        -- bash -c "cd ~/driving/my_trans/gstream && /bin/python3 main_receive.py"
#          ↑       ↑                                  ↑                ↑
#          --     用bash  先进入正确目录              退出conda        运行脚本