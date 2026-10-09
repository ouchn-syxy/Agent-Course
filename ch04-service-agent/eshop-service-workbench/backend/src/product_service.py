"""
商品查询服务。

从预置 JSON 文件加载商品数据，提供查询接口。
"""

import json
from pathlib import Path
from typing import Optional


class ProductService:
    """商品查询服务。"""

    def __init__(self, data_path: Optional[Path] = None) -> None:
        if data_path is None:
            data_path = Path(__file__).parent.parent / "data" / "products.json"
        with open(data_path, "r", encoding="utf-8") as f:
            self._products: list[dict] = json.load(f)

    def list_all(self) -> list[dict]:
        """获取全部商品列表。"""
        return self._products

    def get_by_id(self, product_id: str) -> Optional[dict]:
        """根据 ID 查询单个商品。"""
        for p in self._products:
            if p["id"] == product_id:
                return p
        return None

    def search(self, keyword: str) -> list[dict]:
        """按关键词搜索商品（匹配名称、品类、描述、售后信息）。"""
        kw = keyword.lower()
        results: list[dict] = []
        for p in self._products:
            if (
                kw in p["name"].lower()
                or kw in p["category"].lower()
                or kw in p["description"].lower()
                or self._match_after_sales(p, kw)
            ):
                results.append(p)
        return results

    def _match_after_sales(self, product: dict, keyword: str) -> bool:
        """检查售后信息是否包含关键词。"""
        after_sales = product.get("after_sales")
        if not after_sales:
            return False
        return (
            keyword in after_sales.get("warranty", "").lower()
            or keyword in after_sales.get("return_policy", "").lower()
            or keyword in after_sales.get("notes", "").lower()
        )

    def check_stock(self, product_id: str, size: str, color: str) -> dict:
        """检查指定商品、尺码、颜色的库存情况。"""
        product = self.get_by_id(product_id)
        if not product:
            return {"available": False, "reason": "商品不存在"}
        if size not in product["sizes"]:
            return {"available": False, "reason": f"该商品无 {size} 码"}
        if color not in product["colors"]:
            return {"available": False, "reason": f"该商品无 {color} 颜色"}
        if product["stock"] <= 0:
            return {"available": False, "reason": "库存不足"}
        return {
            "available": True,
            "product": product,
            "stock": product["stock"],
        }
