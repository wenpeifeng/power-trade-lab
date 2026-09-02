"""广州现货/绿证、全国碳市场、国家统计局能源数据解析测试。"""
from __future__ import annotations

import unittest

from crawlers.adapters.carbon_market import parse_carbon_daily
from crawlers.adapters.gzpec_market import (
    parse_green_certificate_weekly,
    parse_spot_weekly,
)
from crawlers.adapters.nbs_energy import parse_nbs_energy_monthly


FETCHED_AT = "2026-07-23T12:00:00+08:00"


class GZPECParserTest(unittest.TestCase):
    def test_spot_weekly_parses_region_and_five_provinces(self):
        html = """
        <h3 class="title">南方区域电力现货市场每周行情一览（2026年7月6日-12日）</h3>
        <div class="txt">
        7月6日-12日，日前市场日均成交电量36.21亿千瓦时，加权均价为319元/兆瓦时。
        实时市场日均成交电量36.29亿千瓦时，加权均价为325元/兆瓦时。
        日前市场，广东、广西、云南、贵州、海南日均成交电量分别为18.19、2.83、11.54、2.64、1.01亿千瓦时，
        加权均价分别为395、235、215、309、396元/兆瓦时。
        实时市场，广东、广西、云南、贵州、海南日均成交电量分别为18.13、2.91、11.56、2.64、1.06亿千瓦时，
        加权均价分别为416、243、202、300、412元/兆瓦时。
        </div>
        """
        rows = parse_spot_weekly(html, "http://example/spot", FETCHED_AT)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0].data_date, "2026-07-12")
        self.assertEqual(rows[0].metrics["day_ahead_avg_price_yuan_mwh"], 319)
        guangdong = next(row for row in rows if row.province == "广东")
        self.assertEqual(guangdong.metrics["real_time_avg_price_yuan_mwh"], 416)
        self.assertEqual(guangdong.provenance_level, "observed_public")

    def test_green_certificate_weekly(self):
        html = """
        <h3 class="title">绿证交易每周行情一览（2026年第27周）</h3>
        <div class="txt">
        2026年06月29日-07月05日，广州电力交易中心平台绿证交易322.8万个；
        交易均价3.45元/个。2026年累计交易量1.63亿个，交易均价4.38元/个。
        绿证交易购入省份排名前五为海南、广西、甘肃、青海、山西，
        绿证交易售出省份排名前五为云南、内蒙、广东、广西、河南。
        光伏项目交易规模为144.08万个，占交易总量44.63%。
        风电项目交易规模为103.33万个，占交易总量的32.01%。
        </div>
        """
        row = parse_green_certificate_weekly(html, "http://example/green", FETCHED_AT)
        self.assertIsNotNone(row)
        self.assertEqual(row.data_date, "2026-07-05")
        self.assertEqual(row.metrics["traded_volume_10k"], 322.8)
        self.assertEqual(row.metrics["ytd_traded_volume_10k"], 16300)


class CarbonParserTest(unittest.TestCase):
    def test_daily_cea_prices_and_volume(self):
        html = """
        <h3 class="article-tit">【CEA】全国碳市场每日综合价格行情及成交信息20260722</h3>
        <div class="article-con">
        今日全国碳市场综合价格行情为: 开盘价90.40元/吨，最高价91.50元/吨，
        最低价90.40元/吨，收盘价91.03元/吨，收盘价较前一日上涨0.54%。
        今日挂牌协议交易成交量211,404吨，成交额19,243,174.00元；
        大宗协议交易成交量615,021吨，成交额55,282,616.00元。
        今日全国碳排放配额总成交量826,425吨，总成交额74,525,790.00元。
        2026年1月1日至7月22日，全国碳市场碳排放配额成交量63,656,947吨，成交额5,006,766,311.94元。
        截至2026年7月22日，全国碳市场碳排放配额累计成交量928,523,467吨，累计成交额62,669,384,543.51元。
        </div>
        """
        row = parse_carbon_daily(html, "https://example/carbon", FETCHED_AT)
        self.assertIsNotNone(row)
        self.assertEqual(row.data_date, "2026-07-22")
        self.assertEqual(row.metrics["close_price"], 91.03)
        self.assertEqual(row.metrics["volume"], 826425)
        self.assertTrue(row.metrics["attribution_required"])

    def test_daily_cea_accepts_official_down_wording(self):
        html = """
        <h3 class="article-tit">【CEA】全国碳市场每日综合价格行情及成交信息20260717</h3>
        <div class="article-con">
        开盘价90.10元/吨，最高价90.11元/吨，最低价90.00元/吨，
        收盘价90.02元/吨，收盘价较前一日下跌0.12%。
        全国碳排放配额总成交量847,645吨，总成交额73,995,250.79元。
        </div>
        """
        row = parse_carbon_daily(html, "https://example/carbon-down", FETCHED_AT)
        self.assertIsNotNone(row)
        self.assertEqual(row.metrics["close_change_pct"], -0.12)


class NBSEnergyParserTest(unittest.TestCase):
    def test_monthly_energy_production(self):
        html = """
        <meta name="ArticleTitle" content="2026年6月份能源生产情况">
        <article>
        6月份，规上工业原煤产量3.8亿吨，同比下降9.7%；日均产量1270万吨。
        6月份，规上工业原油产量1812万吨，同比下降0.5%。
        6月份，规上工业原油加工量5124万吨，同比下降17.7%。
        6月份，规上工业天然气产量214亿立方米，同比增长1.1%。
        6月份，规上工业发电量8276亿千瓦时，同比增长2.0%。
        其中，规上工业火电同比增长0.5%；规上工业水电增长4.8%；
        规上工业核电增长8.5%；规上工业风电下降5.6%；
        规上工业太阳能发电增长14.2%。
        </article>
        """
        row = parse_nbs_energy_monthly(html, "https://example/nbs", FETCHED_AT)
        self.assertIsNotNone(row)
        self.assertEqual(row.data_date, "2026-06")
        self.assertEqual(row.metrics["power_generation_amount"], 8276)
        self.assertEqual(row.metrics["coal_yoy_pct"], -9.7)
        self.assertEqual(row.metrics["wind_power_yoy_pct"], -5.6)


if __name__ == "__main__":
    unittest.main()
