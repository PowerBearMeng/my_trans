# 文件名: gst_receiver_core.py
"""
GStreamer 接收核心模块
封装所有 GStreamer 相关的接收逻辑
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

import struct
import time
from typing import Callable, Optional, Tuple


class GstReceiverCore:
    """GStreamer 接收核心类"""
    
    def __init__(
        self,
        listen_port: int,
        jitter_buffer_latency: int = 200,
        drop_on_latency: bool = False,
        appsink_max_buffers: int = 10,
        verbose: bool = False
    ):
        """
        Args:
            listen_port: 监听端口
            jitter_buffer_latency: 抖动缓冲延迟（毫秒）
            drop_on_latency: 超时是否丢包
            appsink_max_buffers: appsink 最大缓冲数
            verbose: 是否打印详细日志
        """
        self.listen_port = listen_port
        self.verbose = verbose
        
        self.pipeline = None
        self.appsink = None
        self.main_loop = None
        
        # 回调函数
        self.on_packet_received: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        
        # 初始化 GStreamer
        Gst.init(None)
        
        # 创建管道
        self._create_pipeline(jitter_buffer_latency, drop_on_latency, appsink_max_buffers)
    
    def _create_pipeline(self, jitter_buffer_latency: int, drop_on_latency: bool, appsink_max_buffers: int):
        """创建 GStreamer 管道"""
        pipeline_str = (
            f"udpsrc port={self.listen_port} "
            f'caps="application/x-rtp,media=(string)application,clock-rate=(int)90000,encoding-name=(string)X-GST" ! '
            f"rtpjitterbuffer latency={jitter_buffer_latency} drop-on-latency={'true' if drop_on_latency else 'false'} ! "
            f"rtpgstdepay ! "
            f"appsink name=my_sink emit-signals=true sync=false max-buffers={appsink_max_buffers} drop={'true' if drop_on_latency else 'false'}"
        )
        
        if self.verbose:
            print(f"📡 GStreamer 接收管道:")
            print(f"   {pipeline_str}")
            print(f"   Jitter 缓冲: {jitter_buffer_latency} ms")
            print(f"   超时丢包: {'启用' if drop_on_latency else '禁用'}")
            print(f"   Appsink 缓冲: {appsink_max_buffers} 包\n")
        
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.appsink = self.pipeline.get_by_name('my_sink')
        
        # 连接信号
        self.appsink.connect('new-sample', self._on_new_sample)
        
        # 监听管道消息
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)
    
    def _on_bus_message(self, bus, message):
        """处理 GStreamer 总线消息"""
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"❌ GStreamer 错误: {err}")
            if self.verbose:
                print(f"   调试信息: {debug}")
            if self.on_error:
                self.on_error(err, debug)
        elif t == Gst.MessageType.WARNING:
            if self.verbose:
                warn, debug = message.parse_warning()
                print(f"⚠️  GStreamer 警告: {warn}")
        return True
    
    def unpack_metadata(self, packed_data: bytes) -> Tuple[int, float, str, bytes]:
        """
        解包元数据和数据
        格式：[seq(8)][timestamp(8)][filename_len(4)][filename][data]
        """
        sequence_number = struct.unpack('Q', packed_data[:8])[0]
        send_timestamp = struct.unpack('d', packed_data[8:16])[0]
        filename_length = struct.unpack('I', packed_data[16:20])[0]
        filename = packed_data[20:20+filename_length].decode('utf-8')
        data = packed_data[20+filename_length:]
        
        return sequence_number, send_timestamp, filename, data
    
    def _on_new_sample(self, appsink):
        """接收到新样本"""
        sample = appsink.emit('pull-sample')
        if sample:
            buf = sample.get_buffer()
            success, info = buf.map(Gst.MapFlags.READ)
            
            if success:
                try:
                    packed_data = info.data
                    seq, send_time, filename, data = self.unpack_metadata(packed_data)
                    
                    receive_time = time.time()
                    latency_ms = (receive_time - send_time) * 1000
                    
                    if self.on_packet_received:
                        self.on_packet_received(
                            sequence=seq,
                            send_timestamp=send_time,
                            receive_timestamp=receive_time,
                            filename=filename,
                            data=data,
                            packet_size=len(packed_data),
                            latency_ms=latency_ms
                        )
                
                except Exception as e:
                    print(f"❌ 解包失败: {e}")
                    if self.verbose:
                        import traceback
                        traceback.print_exc()
                
                buf.unmap(info)
            
            return Gst.FlowReturn.OK
        
        return Gst.FlowReturn.ERROR
    
    def start(self, main_loop: GLib.MainLoop):
        """启动管道"""
        self.main_loop = main_loop
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("❌ 无法启动 GStreamer 管道")
            return False
        if self.verbose:
            print("✓ GStreamer 管道已启动\n")
        return True
    
    def stop(self):
        """停止管道"""
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.verbose:
            print("✓ GStreamer 管道已停止")


def create_receiver(listen_port: int, **kwargs):
    """便捷函数：创建接收器"""
    return GstReceiverCore(listen_port=listen_port, **kwargs)