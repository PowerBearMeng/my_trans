# 文件名: LidarReceiver.py
import zmq
import msgpack
import time
import numpy as np
import argparse

# --- 核心配置 ---
# 1. 数据通道: DISH (UDP) 必须 BIND
#    "udp://*:5555" 会监听所有网卡 (推荐用于单播和多播接收)
DATA_BIND_ADDR = "udp://*:5555"
#    (如果您确定 Sender 只用多播 "udp://239.1.1.1:5555", 您也可以在这里绑定它)
# DATA_BIND_ADDR = "udp://239.1.1.1:5555"

# 2. ACK 通道: PUSH (TCP) 必须 CONNECT
#    Sender 的 IP 地址将通过命令行参数传入

DATA_GROUP = b"LIDAR"
MAX_FRAME_LAG = 5 # (可选) 缓冲区最多保留5帧，防止内存溢出

class LidarReceiver:
    def __init__(self, sender_ip: str):
        self.context = zmq.Context()

        # --- 数据通道: DISH (UDP) ---
        print(f"正在绑定数据通道 (DISH): {DATA_BIND_ADDR}")
        self.data_socket = self.context.socket(zmq.DISH)
        self.data_socket.bind(DATA_BIND_ADDR)
        self.data_socket.join(DATA_GROUP)
        print(f"已加入 '{DATA_GROUP.decode()}' 组")

        # --- ACK 通道: PUSH (TCP) ---
        ack_connect_addr = f"tcp://{sender_ip}:5556"
        print(f"正在连接 ACK 通道 (PUSH): {ack_connect_addr}")
        self.ack_socket = self.context.socket(zmq.PUSH)
        self.ack_socket.connect(ack_connect_addr)

        # --- 缓冲区 ---
        # { 10: {"type": "pcd", "total": 253, "dtype": ..., "shape_dim": 4, "chunks": {0: bytes, 2: bytes...} } }
        self.reassembly_buffer = {}
        # 跟踪我们正在积极收集的帧ID, 初始化为-1
        self.current_collecting_fid = -1
        # 跟踪我们已处理的最新帧ID，用于丢弃更旧的迟到包
        self.last_processed_fid = -1

    def send_ack(self, frame_id):
        """发送 ACK (TCP)"""
        try:
            ack_msg = {"ack_frame_id": frame_id}
            self.ack_socket.send(msgpack.packb(ack_msg))
        except Exception as e:
            print(f"!! 发送 ACK 失败 (Frame {frame_id}): {e}")

    def process_frame_data(self, frame_id, data):
        """
        (您的核心处理逻辑)
        这就是您“拿到数据”的地方。
        """
        if data["type"] == "json":
            print(f"✔️ [处理 Frame {frame_id}] 收到 JSON 数据")
            json_data = data["data"]
            # print(json_data) # 例如: 打印 JSON 内容

        elif data["type"] == "pcd":
            total_chunks = data["total"]
            chunks = data["chunks"]
            received_chunks = len(chunks)
            dtype = data["dtype"]
            shape_dim = data["shape_dim"]

            if received_chunks < total_chunks:
                # --- 这就是您想要的 "优雅降级" ---
                print(f"⚠️ [处理 Frame {frame_id}] 数据不完整! ({received_chunks}/{total_chunks} 块)")
            else:
                print(f"✔️ [处理 Frame {frame_id}] 数据已完整重组 ({received_chunks}/{total_chunks} 块)")

            # 1. 无论如何，都重组我们所拥有的数据
            all_chunks_bytes = []
            for i in sorted(chunks.keys()): # 按 chunk_index 排序确保顺序
                all_chunks_bytes.append(chunks[i])

            if not all_chunks_bytes:
                print(f"  > Frame {frame_id} 没有收到任何数据块。")
                return # 没有数据可处理

            # 2. 从原始字节重建 NumPy 数组
            try:
                full_data_bytes = b"".join(all_chunks_bytes)
                # 使用 shape_dim 来确定最后一维的大小 (3 for XYZ, 4 for XYZI)
                final_array = np.frombuffer(full_data_bytes, dtype=dtype).reshape(-1, shape_dim)

                print(f"  > 最终数据 shape: {final_array.shape}")

                # -------------------------------------------------
                #
                #   >>> 这是您拿到数据的地方 <<<
                #   在这里调用您自己的处理函数，例如:
                #   my_lidar_processor(frame_id, final_array)
                #   (final_array 是一个 (N, 3 或 4) 的 NumPy 数组)
                #
                # -------------------------------------------------

            except Exception as e:
                print(f"!! 重组 Frame {frame_id} (NumPy) 失败: {e}")

    def process_and_clear_frame(self, frame_id):
        """ 帮助函数：处理并清空缓冲区的特定帧 """
        if frame_id in self.reassembly_buffer:
            print(f"--- 触发处理第 {frame_id} 帧 ---")
            frame_data = self.reassembly_buffer.pop(frame_id)
            self.process_frame_data(frame_id, frame_data)
            self.send_ack(frame_id)
            self.last_processed_fid = max(self.last_processed_fid, frame_id) # 更新处理标记
        # else:
            # print(f"  > (尝试处理第 {frame_id} 帧，但它已不在缓冲区)")

    def run(self):
        print("接收端启动，使用'混合 Marker/新帧 触发'逻辑...")
        # --- 核心改动 1: 将 try...except KeyboardInterrupt 移到最外层 ---
        try:
            while True:
                # --- 核心改动 2: 使用非阻塞 recv ---
                try:
                    # 尝试接收数据，但不阻塞
                    packed_data = self.data_socket.recv(flags=zmq.NOBLOCK)
                except zmq.Again:
                    # --- 核心改动 3: 如果没有数据，短暂休眠 ---
                    # 这给了 Python 解释器机会去响应 Ctrl+C
                    time.sleep(0.001) # 休眠1毫秒，避免CPU空转
                    continue # 继续下一次循环，尝试接收
                except KeyboardInterrupt: # (可选) 也可以在这里捕捉中断
                     print("\n在 recv 中检测到 Ctrl+C...")
                     break # 跳出 while 循环

                # --- 如果收到数据，则执行后续逻辑 (不变) ---
                # 2. 解包
                try:
                    msg = msgpack.unpackb(packed_data, raw=False)
                    frame_id = msg.get("frame_id")
                    marker = msg.get("marker", False)
                    if frame_id is None: continue
                except Exception as e:
                    print(f"!! 消息解包失败: {e}")
                    continue

                # 3. 丢弃旧数据
                if frame_id <= self.last_processed_fid: continue

                # 4. 触发器 B: “下一帧”触发
                if frame_id > self.current_collecting_fid:
                    if self.current_collecting_fid != -1:
                        self.process_and_clear_frame(self.current_collecting_fid)
                    for fid in list(self.reassembly_buffer.keys()):
                        if fid < frame_id:
                            self.process_and_clear_frame(fid)
                    self.current_collecting_fid = frame_id

                # 5. 将当前包存入缓冲区
                if frame_id == self.current_collecting_fid:
                    frag_info = msg.get("frag_info")
                    if frag_info is None: # JSON
                        if frame_id not in self.reassembly_buffer:
                            self.reassembly_buffer[frame_id] = {"type": "json", "data": msg.get("json_data")}
                    else: # PCD Chunk
                        if frame_id not in self.reassembly_buffer:
                            self.reassembly_buffer[frame_id] = {
                                "type": "pcd", "total": frag_info["total_chunks"],
                                "dtype": frag_info["dtype"], "shape_dim": frag_info["shape"][1],
                                "chunks": {} }
                        chunk_index = frag_info.get("chunk_index")
                        pcd_bytes = msg.get("pcd_chunk_bytes")
                        if "chunks" in self.reassembly_buffer[frame_id]:
                             if chunk_index not in self.reassembly_buffer[frame_id]["chunks"]:
                                 self.reassembly_buffer[frame_id]["chunks"][chunk_index] = pcd_bytes

                # 6. 触发器 A: “完整性”触发 (通过 Marker 位)
                if marker and frame_id == self.current_collecting_fid:
                    print(f"  > (收到第 {frame_id} 帧的 Marker 位! 立即处理)")
                    self.process_and_clear_frame(frame_id)
                    # (保持 current_collecting_fid 不变, 等待下一帧的第一个包来更新)

                # 7. 缓冲区溢出保护
                while len(self.reassembly_buffer) > MAX_FRAME_LAG:
                    fid_to_drop = min(self.reassembly_buffer.keys())
                    print(f"!! 缓冲区溢出, 丢弃第 {fid_to_drop} 帧")
                    self.process_and_clear_frame(fid_to_drop)

        # --- 核心改动 1 (续): try 块结束 ---
        except KeyboardInterrupt:
            print("\n检测到 Ctrl+C, 关闭接收端...")
            # (可选) 处理最后剩余正在收集的帧
            if self.current_collecting_fid != -1 and self.current_collecting_fid in self.reassembly_buffer:
                print("处理最后正在收集的帧...")
                self.process_and_clear_frame(self.current_collecting_fid)

        finally:
            print("正在关闭套接字...")
            self.data_socket.close()
            self.ack_socket.close()
            self.context.term()
            print("接收端已关闭。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZMQ LiDAR 接收端 (RADIO/DISH + PUSH/PULL)")
    parser.add_argument("-s", "--sender_ip", type=str, default="10.0.0.2",
                        help="发送端 (LidarSender) 的 IP 地址 (用于 ACK 通道)。")
    args = parser.parse_args()

    receiver = LidarReceiver(sender_ip=args.sender_ip)
    receiver.run()