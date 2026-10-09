from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Any, Dict

from gradio_client import Client, handle_file

from inherit.utils.path import get_prj_root
from inherit.utils.retry import retry


class EmotionControlMethod(Enum):
	"""情感控制方式枚举"""
	SAME_AS_VOICE = "Same as the voice reference"  # 与声音参考一致
	USE_EMO_REF_AUDIO = "Use emotion reference audio"  # 使用情感参考音频
	USE_EMO_VECTORS = "Use emotion vectors"  # 使用情感向量


@dataclass
class EmotionVectors:
	"""
	情感向量参数配置
	数值范围通常在 0-1 之间，视具体模型而定
	"""
	happy: float = 0.0  # vec1: 开心
	angry: float = 0.0  # vec2: 生气
	sad: float = 0.0  # vec3: 悲伤
	afraid: float = 0.0  # vec4: 害怕
	disgusted: float = 0.0  # vec5: 厌恶
	melancholic: float = 0.0  # vec6: 忧郁
	surprised: float = 0.0  # vec7: 惊讶
	calm: float = 0.0  # vec8: 平静


@dataclass
class GenerationParams:
	"""
	音频生成的高级参数配置
	"""
	max_text_tokens_per_segment: float = 120  # 每个片段的最大文本 token 数
	do_sample: bool = True  # param_16: 是否采样
	top_p: float = 0.8  # param_17: Top-P 采样
	top_k: float = 30  # param_18: Top-K 采样
	temperature: float = 0.8  # param_19: 温度参数
	length_penalty: float = 0.0  # param_20: 长度惩罚
	num_beams: float = 3  # param_21:集束搜索数量
	repetition_penalty: float = 10.0  # param_22: 重复惩罚
	max_mel_tokens: float = 1500  # param_23: 最大 Mel token 数


class TTSClient:
	"""
	语音合成接口封装客户端
	"""


	def __init__(self, base_url: str):
		"""
		初始化客户端
		:param base_url: Gradio 服务地址
		"""
		self.client: Client = Client(base_url)


	@retry(max_retries=3, delay_s=2)
	def generate_single(
			self,
			output_path: Path,
			text: str,
			voice_ref_path: Path | str,
			emo_control_method: EmotionControlMethod = EmotionControlMethod.SAME_AS_VOICE,
			emo_ref_path: Optional[Path | str] = None,
			emo_weight: float = 0.65,
			emotion_vectors: Optional[EmotionVectors] = None,
			emotion_description: str = "",
			randomize_emotion: bool = False,
			gen_params: Optional[GenerationParams] = None
	) -> None:
		"""
		调用 /gen_single 接口生成语音

		:param output_path 输出文件路径

		:param text: 需要合成的文本内容
		:param voice_ref_path: 声音参考音频文件的本地路径或 URL (用于克隆音色)
		:param emo_control_method: 情感控制方式
		:param emo_ref_path: 情感参考音频文件的本地路径或 URL (仅当 method 为 USE_EMO_REF_AUDIO 或需要辅助时使用)
							 如果未提供且 method 需要，默认使用 voice_ref_path
		:param emo_weight: 情感控制权重 (默认 0.65)
		:param emotion_vectors: 情感向量配置 (仅当 method 为 USE_EMO_VECTORS 时生效)，默认为全0
		:param emotion_description: 情感描述文本 (emo_text)
		:param randomize_emotion: 是否随机采样情感 (emo_random)
		:param gen_params: 生成参数配置，如果为 None 则使用默认值
		"""

		# 参数默认值处理
		if emotion_vectors is None:
			emotion_vectors: EmotionVectors = EmotionVectors()

		if gen_params is None:
			gen_params: GenerationParams = GenerationParams()

		# 调用 Gradio 接口
		# 注意：gradio_client 的 handle_file 可以处理 URL 或本地路径
		result: Dict[str, Any] = self.client.predict(
			emo_control_method=emo_control_method.value,
			prompt=handle_file(voice_ref_path),
			text=text,
			emo_ref_path=handle_file(emo_ref_path) if emo_ref_path else None,
			emo_weight=emo_weight,

			# 展开情感向量
			vec1=emotion_vectors.happy,
			vec2=emotion_vectors.angry,
			vec3=emotion_vectors.sad,
			vec4=emotion_vectors.afraid,
			vec5=emotion_vectors.disgusted,
			vec6=emotion_vectors.melancholic,
			vec7=emotion_vectors.surprised,
			vec8=emotion_vectors.calm,

			emo_text=emotion_description,
			emo_random=randomize_emotion,

			# 展开生成参数
			max_text_tokens_per_segment=gen_params.max_text_tokens_per_segment,
			param_16=gen_params.do_sample,
			param_17=gen_params.top_p,
			param_18=gen_params.top_k,
			param_19=gen_params.temperature,
			param_20=gen_params.length_penalty,
			param_21=gen_params.num_beams,
			param_22=gen_params.repetition_penalty,
			param_23=gen_params.max_mel_tokens,

			api_name="/gen_single"
		)
		if result and "value" in result:
			# 将生成文件保存到 output_path
			output_filepath: str = result["value"]
			shutil.copyfile(output_filepath, output_path)
		else:
			raise RuntimeError("TTS 生成失败：服务返回空结果")


# ============================================================
# Demo
# ============================================================

if __name__ == "__main__":
	from config import Config

	cfg: Config = Config.from_yaml()
	if cfg.tts is None:
		raise ValueError("缺少 tts 配置.")

	client: TTSClient = TTSClient(base_url=cfg.tts.base_url)
	print(f"TTS 服务: {cfg.tts.base_url}")
	print(f"声音参考: {cfg.tts.voice_ref_path or '(未配置 voice_ref_path)'}")
	print()

	output_path: Path = get_prj_root() / "output" / "tts" / "tts_demo.wav"
	try:
		client.generate_single(
			output_path=output_path,
			text="你好，这是一段语音合成测试。",
			voice_ref_path=cfg.tts.voice_ref_path,
		)
		print("✅ 语音已保存至 output/tts_demo.wav")
	except Exception as e:
		print(f"❌ 合成失败（请确认 index-tts-2 服务已启动）: {e}")
