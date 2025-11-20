# 🌍 App Store Price Scraper - Claude Max 订阅价格爬虫

一个强大的 App Store 价格爬虫系统，用于获取全球各国 Claude Max 应用的订阅价格，并找出最便宜的购买地区。

## ✨ 功能特性

- 🌐 **多国价格爬取**: 自动获取全球多个国家和地区的 App Store 价格
- 💱 **实时汇率转换**: 将所有价格统一转换为美元进行比较
- 📊 **价格分析**: 自动分析并找出最便宜的购买地区
- 💾 **数据持久化**: 使用 SQLite 数据库存储历史价格数据
- ⏰ **定时更新**: 支持定时任务自动更新价格信息
- 📈 **价格趋势**: 追踪价格变化趋势

## 🚀 快速开始

### 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 配置

复制环境变量配置文件：
```bash
cp .env.example .env
```

编辑 `.env` 文件，配置你的设置（如有需要）。

### 运行

```bash
# 运行一次价格爬取
python main.py --mode once

# 启动定时任务（每天更新）
python main.py --mode schedule

# 只显示分析结果
python main.py --mode analyze
```

## 📁 项目结构

```
app-store-price-scraper/
├── src/
│   ├── scrapers/          # 爬虫模块
│   │   ├── app_store.py   # App Store 爬虫核心
│   │   └── regions.py     # 国家/地区配置
│   ├── converters/        # 转换模块
│   │   ├── currency.py    # 货币转换
│   │   └── exchange_rate.py # 汇率获取
│   ├── analyzers/         # 分析模块
│   │   └── price_analyzer.py # 价格分析
│   ├── storage/           # 数据存储
│   │   ├── database.py    # 数据库操作
│   │   └── models.py      # 数据模型
│   └── scheduler/         # 定时任务
│       └── tasks.py
├── config/               # 配置文件
│   ├── regions.json      # 地区配置
│   └── settings.py       # 系统配置
├── data/                 # 数据目录
│   └── prices.db         # SQLite 数据库
├── tests/               # 测试文件
├── .env                 # 环境变量配置
├── .env.example         # 环境变量示例
├── requirements.txt     # Python 依赖
├── main.py             # 主程序入口
└── README.md           # 项目文档
```

## 🎯 支持的国家/地区

系统支持以下国家和地区的价格爬取：

- 🇺🇸 美国 (US) - 基准价格
- 🇮🇳 印度 (IN)
- 🇹🇷 土耳其 (TR)
- 🇦🇷 阿根廷 (AR)
- 🇧🇷 巴西 (BR)
- 🇩🇪 德国 (DE)
- 🇫🇷 法国 (FR)
- 🇬🇧 英国 (GB)
- 🇯🇵 日本 (JP)
- 🇨🇦 加拿大 (CA)
- 🇦🇺 澳大利亚 (AU)
- 🇨🇳 中国 (CN)
- 更多...

## 📊 使用示例

### Python API

```python
from src.scrapers.app_store import AppStoreScraper
from src.analyzers.price_analyzer import PriceAnalyzer

# 创建爬虫实例
scraper = AppStoreScraper()

# 爬取价格
prices = scraper.scrape_all_regions()

# 分析价格
analyzer = PriceAnalyzer()
results = analyzer.analyze(prices)

# 显示最便宜的地区
print(f"最便宜的地区: {results['cheapest']['region']}")
print(f"价格: ${results['cheapest']['price_usd']:.2f} USD")
```

## ⚙️ 配置选项

在 `config/settings.py` 中可以配置：

- `APP_ID`: Claude Max 应用的 App Store ID
- `SCRAPE_INTERVAL`: 爬取间隔时间
- `TIMEOUT`: 请求超时时间
- `RETRY_TIMES`: 重试次数
- `USE_PROXY`: 是否使用代理

## 🔧 技术栈

- **Python 3.8+**
- **Playwright**: 浏览器自动化
- **SQLAlchemy**: ORM 数据库操作
- **Pandas**: 数据处理和分析
- **APScheduler**: 定时任务调度
- **BeautifulSoup4**: HTML 解析

## 📝 注意事项

1. 首次运行需要安装 Playwright 浏览器
2. 爬取频率不要过高，建议每天 1-2 次
3. 某些地区可能需要代理才能访问
4. 汇率数据使用第三方 API，有请求限制

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

感谢所有开源项目的贡献者！
