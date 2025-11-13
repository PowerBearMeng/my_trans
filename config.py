# 文件名: config.py
"""
配置文件 - 所有可调参数集中在这里
"""
import time
# ============= 网络配置 =============
TARGET_HOST = '10.0.0.2'
TARGET_PORT = 5004

FEEDBACK_HOST = '10.0.0.1'
FEEDBACK_PORT = 5005
# ============= 发送端配置 =============
# 数据源
# SOURCE_FOLDER = '/home/mfh/driving/my_mot/pcd/0825/test_i_02_renamed'
SOURCE_FOLDER = '/home/mfh/driving/my_mot/fused_output/0825_test_02_double'
# SOURCE_FOLDER = '/home/mfh/driving/code/RCPCC/output/compressed'
# SOURCE_FOLDER = '/home/mfh/driving/my_mot/pcd/0825/i'
FILE_EXTENSION = '.pcd'  # 支持 .pcd, .bin, .json 等任意格式
LOOP_FILES = False        # 是否循环发送

# 发送参数
SEND_RATE_HZ = 10        # 发送频率（Hz）

# GStreamer 缓冲区设置
SENDER_BUFFER_SIZE_MB = 4                # UDP 发送缓冲区（MB）
SENDER_QUEUE_MAX_BUFFERS = 2            # 队列最大缓冲包数
SENDER_QUEUE_LEAKY = False                # 队列满时是否丢弃旧包

# RTT 测量配置
RTT_MEASUREMENT_ENABLED = True           # ← 新增：是否启用 RTT 测量
RTT_FEEDBACK_INTERVAL = 1.0              # ← 新增：反馈间隔（秒

# 统计输出
SENDER_CSV = '../stats/sender_stats/1106/' + time.strftime("%Y%m%d_%H%M%S") + '.csv'
SENDER_STATS_PRINT_INTERVAL = 5.0        # 统计打印间隔（秒）

# ============= 接收端配置 =============
# 输出设置
OUTPUT_FOLDER = '../received_pcd'
RECEIVER_CSV = '../stats/receiver_stats/' + time.strftime("_%Y%m%d_%H%M%S") + '.csv'

# GStreamer 缓冲区设置
RECEIVER_JITTER_BUFFER_LATENCY = 100     # 抖动缓冲延迟（毫秒）
RECEIVER_DROP_ON_LATENCY = True          # 超时是否丢包
RECEIVER_APPSINK_MAX_BUFFERS = 2        # appsink 最大缓冲

# 统计输出
RECEIVER_STATS_PRINT_INTERVAL = 5.0      # 统计打印间隔（秒）

# ============= 调试选项 =============
VERBOSE = True           # 是否打印详细日志
SAVE_FILES = False  # 接收端是否保存文件