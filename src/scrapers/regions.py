"""
国家/地区管理模块
"""
import json
from pathlib import Path
from typing import List, Dict, Optional

class Region:
    """地区信息类"""

    def __init__(self, code: str, name: str, name_cn: str, currency: str,
                 store_front: str, locale: str):
        self.code = code
        self.name = name
        self.name_cn = name_cn
        self.currency = currency
        self.store_front = store_front
        self.locale = locale

    def __repr__(self):
        return f"Region({self.code}, {self.name}, {self.currency})"

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "code": self.code,
            "name": self.name,
            "name_cn": self.name_cn,
            "currency": self.currency,
            "store_front": self.store_front,
            "locale": self.locale
        }


class RegionManager:
    """地区管理器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化地区管理器

        Args:
            config_path: 配置文件路径，默认使用项目中的 regions.json
        """
        if config_path is None:
            # 默认配置文件路径
            base_dir = Path(__file__).resolve().parent.parent.parent
            config_path = base_dir / "config" / "regions.json"

        self.config_path = Path(config_path)
        self.regions: List[Region] = []
        self._load_regions()

    def _load_regions(self):
        """从配置文件加载地区信息"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for region_data in data.get("regions", []):
                region = Region(
                    code=region_data["code"],
                    name=region_data["name"],
                    name_cn=region_data["name_cn"],
                    currency=region_data["currency"],
                    store_front=region_data["store_front"],
                    locale=region_data["locale"]
                )
                self.regions.append(region)

        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件 JSON 格式错误: {e}")

    def get_all_regions(self) -> List[Region]:
        """获取所有地区"""
        return self.regions

    def get_region_by_code(self, code: str) -> Optional[Region]:
        """
        根据地区代码获取地区信息

        Args:
            code: 地区代码，如 'us', 'cn' 等

        Returns:
            Region 对象，如果不存在返回 None
        """
        code = code.lower()
        for region in self.regions:
            if region.code.lower() == code:
                return region
        return None

    def get_region_by_currency(self, currency: str) -> List[Region]:
        """
        根据货币代码获取所有使用该货币的地区

        Args:
            currency: 货币代码，如 'USD', 'EUR' 等

        Returns:
            使用该货币的地区列表
        """
        currency = currency.upper()
        return [r for r in self.regions if r.currency.upper() == currency]

    def get_region_codes(self) -> List[str]:
        """获取所有地区代码列表"""
        return [r.code for r in self.regions]

    def get_region_names(self) -> List[str]:
        """获取所有地区名称列表"""
        return [r.name for r in self.regions]

    def count(self) -> int:
        """获取地区总数"""
        return len(self.regions)

    def __len__(self):
        return self.count()

    def __iter__(self):
        return iter(self.regions)

    def __getitem__(self, index):
        return self.regions[index]


# 创建全局地区管理器实例
region_manager = RegionManager()


if __name__ == "__main__":
    # 测试代码
    manager = RegionManager()
    print(f"加载了 {manager.count()} 个地区")
    print("\n所有地区:")
    for region in manager:
        print(f"  {region.code}: {region.name_cn} ({region.name}) - {region.currency}")

    # 测试获取特定地区
    us_region = manager.get_region_by_code("us")
    if us_region:
        print(f"\n美国地区信息: {us_region}")

    # 测试获取欧元区国家
    eur_regions = manager.get_region_by_currency("EUR")
    print(f"\n欧元区国家: {[r.name for r in eur_regions]}")
