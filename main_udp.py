# 文件名: main_udp.py
import argparse
import time
from io_feeder import folder_feeder 
from zmq_send.LidarSender import LidarSender 

def main():
    parser = argparse.ArgumentParser(description="ZMQ 数据发送端 (RTP-like, RADIO/UDP)")
    
    parser.add_argument("-d", "--directory", type=str,
                        default="/home/mfh/driving/my_mot/pcd/0825/test_i_02_renamed",
                        help="包含数据文件的文件夹路径。")
    parser.add_argument("--ext", type=str, default=".pcd",
                        help="要发送的文件扩展名 (e.g., .pcd, .json)")
    
    # --- 核心: 确保你使用的是 -c/--connect 并且地址是 *具体* 的 ---
    parser.add_argument("-c", "--connect", type=str, 
                        default="udp://10.0.0.1:5555", # 本地测试
                        # default="udp://239.1.1.1:5555", # 多播
                        help="发送数据连接的UDP地址 (e.g., 'udp://127.0.0.1:5555')")
    
    parser.add_argument("-a", "--ack_bind", type=str, default="tcp://*:5556",
                        help="接收 ACK 的绑定地址 (TCP)。")
    parser.add_argument("-r", "--rate", type=int, default=10,
                        help="发送频率 (Hz)。")
    
    args = parser.parse_args()

    # LidarSender 实例化
    sender = LidarSender(connect_address=args.connect,
                         ack_bind_address=args.ack_bind)

    # io_feeder 调用
    data_producer = folder_feeder(folder_path=args.directory,
                                  extension=args.ext)

    print(f"准备发送，将以 {args.rate} Hz 的频率进行...")
    time.sleep(1)

    # "胶水" 逻辑
    try:
        for data_key, data_payload, source_info in data_producer:
            sender.send_frame(data_key, data_payload, source_info)
            time.sleep(1.0 / args.rate)
            
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，正在关闭程序...")
    finally:
        sender.close()

if __name__ == "__main__":
    main()