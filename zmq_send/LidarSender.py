# 文件名: zmq_send/LidarSender.py
import zmq
import msgpack
import time
import numpy as np
import threading

# --- 核心修复: 使用一个非常小的、安全的块大小 ---
# ( 1500 点 * 4 个 float32 [X,Y,Z,I] * 4 字节/float32 = 24000 字节 )
# 这和您成功的日志 (2922 bytes) 非常吻合
POINTS_PER_CHUNK = 500

class LidarSender:
    def __init__(self, connect_address: str, ack_bind_address: str = "tcp://*:5556"):
        print("正在初始化 ZeroMQ 发送端 (RADIO-UDP 数据, PULL-TCP ACK)...")
        self.context = zmq.Context()
        self.send_socket = self.context.socket(zmq.RADIO)
        self.send_socket.setsockopt(zmq.SNDHWM, 100)
        self.send_socket.connect(connect_address)
        print(f"✔️ [数据通道] 已连接到 {connect_address} (UDP) (RADIO)")
        self.ack_socket = self.context.socket(zmq.PULL)
        self.ack_socket.bind(ack_bind_address)
        print(f"✔️ [控制通道] 已在 {ack_bind_address} (TCP) 上绑定用于接收 ACK (PULL)")
        
        # ... (ACK 线程 和 __init__ 的其余部分不变) ...
        self.frame_id = 0
        self.sent_timestamps = {}
        self.rtt_records_ms = []
        self._stop_event = threading.Event()
        self.ack_thread = threading.Thread(target=self._ack_listener, daemon=True)
        self.ack_thread.start()

    def _ack_listener(self):
        # ... (此函数完全不变) ...
        while not self._stop_event.is_set():
            try:
                packed_ack = self.ack_socket.recv(flags=zmq.NOBLOCK)
            except zmq.Again: time.sleep(0.001); continue
            try:
                ack_data = msgpack.unpackb(packed_ack, raw=False)
                ack_frame_id = ack_data.get("ack_frame_id")
            except Exception: continue
            if ack_frame_id is not None and ack_frame_id in self.sent_timestamps:
                send_time = self.sent_timestamps.pop(ack_frame_id)
                rtt = (time.monotonic() - send_time) * 1000.0
                self.rtt_records_ms.append(rtt)
                print(f"[ACK线程] 收到 Frame {ack_frame_id} 的 ACK, RTT: {rtt:.2f} ms   ", end="\r")

    def send_frame(self, data_key: str, data_payload: object, source_info: str):
        send_time = time.monotonic()
        # 假设接收端在处理完一帧 (即使不完整) 后才发 ACK
        self.sent_timestamps[self.frame_id] = send_time

        if data_key == "json_data":
            # --- 路径 A: JSON (不变) ---
            message_data = {
                "frame_id": self.frame_id, "timestamp_monotonic_s": send_time,
                "source_file": source_info, "frag_info": None, 
                "json_data": data_payload,
                "marker": True # 单包消息本身就是结束
            }
            packed_message = msgpack.packb(message_data, use_bin_type=True)
            self.send_socket.send(packed_message, group=b"LIDAR")
            print(f"已发送第 {self.frame_id} 帧 ({source_info}, 大小：{len(packed_message)} bytes) [单包]")

        elif data_key == "pcd_data":
            # --- 路径 B: PCD (核心修复) ---
            np_data = data_payload # {"points": (N,3), "intensities": (N,)}
            np_points = np_data["points"]
            np_intensities = np_data["intensities"]
            
            # --- 核心修复: 将 (N,3) 和 (N,) 合并为 (N, 4) ---
            if np_intensities is not None and len(np_intensities) == len(np_points):
                # .reshape(-1, 1) 确保 (N,) -> (N, 1) 以便 hstack
                combined_array = np.hstack((np_points, np_intensities.reshape(-1, 1)))
                dtype = str(combined_array.dtype) # "float32"
                shape = (-1, 4) # (100, 4)
            else:
                # 如果没有 intensity, 只发送 XYZ
                combined_array = np_points
                dtype = str(combined_array.dtype) # "float32"
                shape = (-1, 3) # (100, 3)

            total_points = len(combined_array)
            total_chunks = (total_points + POINTS_PER_CHUNK - 1) // POINTS_PER_CHUNK
            
            print(f"正在发送第 {self.frame_id} 帧 ({source_info}, {total_points} 个点 -> {total_chunks} 块)...")

            for i in range(total_chunks):
                start = i * POINTS_PER_CHUNK
                end = min((i + 1) * POINTS_PER_CHUNK, total_points)
                chunk_array = combined_array[start:end]
                
                # --- 核心修复: 使用 .tobytes() ---
                chunk_payload_bytes = chunk_array.tobytes()
                is_last_chunk = (i == total_chunks - 1)
                message_data = {
                    "frame_id": self.frame_id,
                    "timestamp_monotonic_s": send_time,
                    "source_file": source_info,
                    "frag_info": { 
                        "total_chunks": total_chunks,
                        "chunk_index": i,
                        "dtype": dtype, 
                        "shape": (chunk_array.shape[0], shape[1]) # (e.g., (100, 4))
                    },
                    "pcd_chunk_bytes": chunk_payload_bytes,
                    "marker": is_last_chunk # <--- 在最后一个块标记为 True
                }
                
                packed_message = msgpack.packb(message_data, use_bin_type=True)
                
                # 现在这个包的大小会是 100*4*4 + 元数据 ≈ 1.7KB
                # 这将 100% 稳定
                
                try:
                    self.send_socket.send(packed_message, group=b"LIDAR")
                    # (日志太刷屏了，可以考虑只打印第一和最后一个)
                    if i == 0 or i == (total_chunks - 1):
                        print(f"  > 已发送第 {self.frame_id} 帧, 块 {i+1}/{total_chunks} ({len(packed_message)} bytes)")
                except Exception as e:
                    print(f"!! [分片] 发送第 {self.frame_id} 帧, 块 {i} 失败: {e}")
        
        self.frame_id += 1

    def close(self):
        # ... (close 函数完全不变) ...
        print("\n正在关闭 ZeroMQ 套接字...")
        self._stop_event.set()
        self.ack_thread.join(timeout=1.0)
        # ... (统计报告不变) ...
        self.send_socket.close()
        self.ack_socket.close()
        self.context.term()
        print("发送端已安全关闭。")