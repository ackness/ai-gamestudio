from __future__ import annotations

from backend.app.services.image_service import _extract_image_payload


_PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2Xh1sAAAAASUVORK5CYII="
)


def test_extract_image_payload_from_markdown_data_url_content():
    raw = {
        "choices": [
            {
                "message": {
                    "content": (
                        "好的，这是一只赛博朋克风格的猫。\n\n"
                        f"![image](data:image/png;base64,{_PNG_1X1_BASE64})"
                    )
                }
            }
        ]
    }
    parsed = _extract_image_payload(raw)
    assert parsed["image_url"].startswith("data:image/png;base64,")


def test_extract_image_payload_from_content_list_text_with_pure_base64():
    raw = {
        "choices": [
            {
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"image payload: {_PNG_1X1_BASE64}",
                        }
                    ]
                }
            }
        ]
    }
    parsed = _extract_image_payload(raw)
    assert parsed["image_url"].startswith("data:image/png;base64,")

