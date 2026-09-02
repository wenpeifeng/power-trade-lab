"""国家能源局公开统计解析器离线测试。"""
from __future__ import annotations

import unittest

from crawlers.adapters.nea_statistics import (
    parse_green_certificate,
    parse_market_transaction,
    parse_new_energy_projects,
    parse_new_energy_project_provinces,
    parse_power_consumption,
    parse_power_statistics,
)


class NEAStatisticsParserTest(unittest.TestCase):
    def test_parse_monthly_power_consumption(self):
        title = "2026年1-6月份全社会用电量同比增长5.3%"
        text = (
            "6月份，全社会用电量8981亿千瓦时，同比增长3.7%。"
            "第一产业用电量136亿千瓦时，同比增长2.0%。"
            "第二产业用电量5734亿千瓦时，同比增长4.7%；"
            "其中，工业用电量5683亿千瓦时。"
            "第三产业用电量1860亿千瓦时。"
            "城乡居民生活用电量1251亿千瓦时，同比下降3.1%。"
            "1～6月，全社会用电量累计50999亿千瓦时。"
        )
        parsed = parse_power_consumption(title, text, "https://www.nea.gov.cn/a", "now")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.data_date, "2026-06")
        self.assertEqual(parsed.metrics["total_consumption_100m_kwh"], 8981)
        self.assertEqual(parsed.metrics["industrial_100m_kwh"], 5683)
        self.assertEqual(parsed.provenance_level, "observed_public")

    def test_parse_monthly_market_transaction(self):
        title = "2026年1-5月全国电力市场交易电量同比增长24.8%"
        text = (
            "2026年5月，全国完成电力市场交易电量6268亿千瓦时，同比增长23.6%。"
            "省内交易电量4906亿千瓦时；跨省跨区交易电量1362亿千瓦时。"
            "中长期交易电量5617亿千瓦时；现货交易电量651亿千瓦时。"
            "绿电交易电量311亿千瓦时。电网企业市场化代理购电电量666亿千瓦时。"
            "2026年1-5月，全国累计完成电力市场交易电量30573亿千瓦时。"
        )
        parsed = parse_market_transaction(title, text, "https://www.nea.gov.cn/b", "now")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.data_date, "2026-05")
        self.assertEqual(parsed.metrics["spot_100m_kwh"], 651)
        self.assertEqual(parsed.metrics["green_power_100m_kwh"], 311)
        self.assertEqual(parsed.metrics["period_scope"], "monthly")

    def test_parse_ytd_market_transaction_when_monthly_breakdown_is_absent(self):
        title = "2026年1-2月全国电力市场交易电量同比增长25.5%"
        text = (
            "2026年1-2月，全国累计完成电力市场交易电量11925亿千瓦时，"
            "同比增长25.5%。从交易范围看，省内交易电量9543亿千瓦时，"
            "跨省跨区交易电量2382亿千瓦时。从交易品种看，中长期交易电量"
            "10337亿千瓦时；现货交易电量1588亿千瓦时。绿电交易电量484亿千瓦时。"
        )
        parsed = parse_market_transaction(title, text, "https://www.nea.gov.cn/ytd", "now")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.data_type, "national_market_transaction_ytd")
        self.assertEqual(parsed.data_date, "2026-02")
        self.assertEqual(parsed.metrics["period_scope"], "year_to_date")
        self.assertEqual(parsed.metrics["spot_100m_kwh"], 1588)

    def test_parse_green_certificate(self):
        title = "国家能源局发布2026年4月全国可再生能源绿色电力证书核发及交易数据"
        text = (
            "2026年4月，国家能源局核发绿证2.37亿个，其中可交易绿证1.77亿个。"
            "2026年4月，全国交易绿证7110万个，其中绿色电力交易绿证2972万个。"
            "2026年4月，全国单独交易绿证4138万个。"
        )
        parsed = parse_green_certificate(title, text, "https://www.nea.gov.cn/c", "now")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.data_date, "2026-04")
        self.assertEqual(parsed.metrics["issued_100m"], 2.37)
        self.assertEqual(parsed.metrics["traded_10k"], 7110)

    def test_parse_power_statistics(self):
        title = "国家能源局发布2026年1-6月份全国电力统计数据"
        text = (
            "截至6月底，全国累计发电装机容量40.4亿千瓦，同比增长10.8%。"
            "其中，太阳能发电装机容量12.7亿千瓦，同比增长15.8%；"
            "风电装机容量6.8亿千瓦，同比增长18.5%。"
            "1-6月份，全国发电设备累计平均利用1392小时，比上年同期降低113小时。"
        )
        parsed = parse_power_statistics(title, text, "https://www.nea.gov.cn/d", "now")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.data_date, "2026-06")
        self.assertEqual(parsed.metrics["solar_installed_capacity_100m_kw"], 12.7)
        self.assertEqual(parsed.metrics["average_utilization_hours_yoy_change"], -113)

    def test_parse_new_energy_projects(self):
        title = "关于2026年6月全国新增建档立卡新能源发电（不含户用光伏）项目情况的公告"
        text = (
            "2026年6月，全国新增建档立卡新能源发电（不含户用光伏）项目共3825个，"
            "其中风电项目32个，光伏发电项目3787个（集中式光伏发电项目36个，"
            "工商业分布式光伏发电项目3751个），生物质发电项目6个。"
        )
        parsed = parse_new_energy_projects(title, text, "https://www.nea.gov.cn/e", "now")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.data_date, "2026-06")
        self.assertEqual(parsed.metrics["total_projects"], 3825)
        self.assertEqual(parsed.metrics["commercial_distributed_solar_projects"], 3751)

    def test_parse_new_energy_project_province_table(self):
        html = """
        <table>
          <tr><th>地区</th><th>风电</th><th>集中式光伏</th>
              <th>工商业分布式光伏</th><th>生物质</th><th>合计</th></tr>
          <tr><td>浙江</td><td>0</td><td>3</td><td>313</td><td>2</td><td>318</td></tr>
          <tr><td>广东</td><td>6</td><td>0</td><td>1,462</td><td>0</td><td>1,468</td></tr>
        </table>
        """
        rows = parse_new_energy_project_provinces(
            html,
            data_date="2026-06",
            title="2026年6月项目情况",
            source_url="https://www.nea.gov.cn/e",
            fetched_at="now",
        )
        self.assertEqual(len(rows), 2)
        zhejiang = next(row for row in rows if row.province == "浙江")
        self.assertEqual(zhejiang.metrics["total_projects"], 318)
        self.assertEqual(zhejiang.metrics["solar_projects"], 316)


if __name__ == "__main__":
    unittest.main()
