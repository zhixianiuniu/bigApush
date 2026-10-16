"""飞书机器人通知"""
import json
import logging
import requests

logger = logging.getLogger(__name__)

# 飞书自定义机器人强制安全校验：每条消息必须含此关键词，否则被静默拒收。
# 这里在发送时强制注入，用户只需在飞书里把「自定义关键词」设为这一个值即可。
SECURE_KEYWORD = "选股信号"


class FeishuNotifier:
    def __init__(self, webhook_url: str = ""):
        self.webhook_url = webhook_url

    def send_text(self, text: str) -> bool:
        if not self.webhook_url:
            logger.warning("飞书 webhook_url 未配置")
            return False
        text = f"【{SECURE_KEYWORD}】\n{text}"
        payload = {"msg_type": "text", "content": {"text": text}}
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            result = resp.json()
            if result.get("code") == 0:
                logger.info("飞书推送成功")
                return True
            logger.error("飞书推送失败: %s", result)
            return False
        except Exception as e:
            logger.error("飞书推送异常: %s", e)
            return False

    def send_post(self, title: str, content_lines: list) -> bool:
        if not self.webhook_url:
            logger.warning("飞书 webhook_url 未配置")
            return False
        title = f"【{SECURE_KEYWORD}】{title}"
        post_content = []
        for line in content_lines:
            post_content.append([{"tag": "text", "text": line}])
        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": post_content
                    }
                }
            }
        }
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            result = resp.json()
            if result.get("code") == 0:
                logger.info("飞书推送成功")
                return True
            logger.error("飞书推送失败: %s", result)
            return False
        except Exception as e:
            logger.error("飞书推送异常: %s", e)
            return False
