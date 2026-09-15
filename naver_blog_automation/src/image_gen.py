import base64
import os
from pathlib import Path
from typing import List, Dict

from openai import OpenAI

from config import OPENAI_IMAGE_MODEL


def generate_images(prompts: List[Dict], out_dir: str, default_size: str = "1536x1024") -> List[Dict]:
    """턴3에서 받은 이미지 프롬프트 각각을 실제 이미지 파일로 만든다.

    prompts 각 항목: {"subheading": str, "prompt": str, "size": str(optional)}
    반환: 성공한 항목만 {"subheading", "prompt", "file_path"} 형태로 담아 돌려준다.
    실패한 프롬프트(예: 안전 정책 거부)는 건너뛰고 콘솔에 이유를 출력한다 —
    한 장이 실패해도 나머지 이미지 생성과 포스팅 자체는 계속 진행되게 하기 위함이다.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    results = []
    for i, item in enumerate(prompts):
        prompt_text = item["prompt"]
        img_size = item.get("size") or default_size
        try:
            response = client.images.generate(
                model=OPENAI_IMAGE_MODEL,
                prompt=prompt_text,
                size=img_size,
                n=1,
            )
            b64 = response.data[0].b64_json
            file_path = os.path.join(out_dir, f"image_{i + 1:02d}.png")
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(b64))
            results.append({**item, "file_path": file_path})
            print(f"  이미지 생성 완료: {file_path} ({item.get('subheading', '')})")
        except Exception as e:
            print(f"  [경고] 이미지 생성 실패 (건너뜀) - {item.get('subheading', '')}: {e}")
            continue

    return results
