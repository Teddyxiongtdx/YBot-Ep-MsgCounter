from ErisPulse import sdk
from ErisPulse.Core.Bases import BaseModule
from ErisPulse.loaders import ModuleLoadStrategy
from datetime import datetime, timedelta
import json


class Main(BaseModule):
    def __init__(self):
        self.sdk = sdk
        self.logger = sdk.logger
        self.storage = sdk.storage

        self.counter = {}
        self.count = 0

    @staticmethod
    def get_load_strategy():
        return ModuleLoadStrategy(
            lazy_load=False,
            priority=0,
            depends=[]
        )
    
    async def on_load(self, event):
        self.counter = self._load_counter()
        self._register()
        self.logger.info("MsgCounter模块已加载")

    async def on_unload(self, event):
        self._save_counter()
        self.logger.info("MsgCounter模块已卸载")
    
    # 一、数据库
    # 1.可爱的默认值
    @classmethod
    def _default_counter(cls):
        return {
            "messages": {"_total": 0},
            "notices": {"_total": 0},
            "requests": {"_total": 0},
            "GroupEnter": {}
        }

    # 2.增加记录并自动维护所有total
    @staticmethod
    def _add_record(counter, platform, date, uid, gid):
        counter["_total"] = counter.get("_total", 0) + 1
        p = counter.setdefault(platform, {'_total': 0})
        p['_total'] += 1
        d = p.setdefault(date, {'_total': 0})
        d['_total'] += 1

        users = d.setdefault('users', {})
        user = users.setdefault(uid, {'_total': 0})
        user['_total'] += 1
        user[gid] = user.get(gid, 0) + 1

        groups = d.setdefault('groups', {})
        group = groups.setdefault(gid, {'_total': 0})
        group['_total'] += 1
        group[uid] = group.get(uid, 0) + 1
    
    @staticmethod
    def _add_record_enter(counter, platform, uid, gid):
        p = counter.setdefault(platform, {})
        group = p.setdefault(gid, {})
        group[uid] = group.get(uid, 0) + 1

    # s1.加载器
    def _load_counter(self):
        try:
            stored = self.sdk.storage.get("__ep_counter_data__", {})
            if not stored:
                return Main._default_counter()
            return stored
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            self.logger.error(f"加载统计数据时出错: {e}")
            return Main._default_counter()

    # s2.持久器
    def _save_counter(self):
        try:
            self.storage.set("__ep_counter_data__", self.counter)
            self.logger.debug(f"统计已保存")
            return True
        except (TypeError, ValueError) as e:
            print(f"Failed to save counter: {e}")
            return False


    # 二、古希腊掌管信息的神
    def _register(self):
        @sdk.adapter.on("message")
        async def on_message(data):
            platform = data.get('platform', 'unknown')
            date = datetime.now().strftime("%y%m%d")
            uid = data.get('user_id', 'default_user_id')
            gid = data.get('group_id', 'default_group_id')
            Main._add_record(self.counter["messages"], platform, date, uid, gid)
            self.count += 1
            if self.count%10==0:
                self._save_counter()

        @sdk.adapter.on("notice")
        async def on_notice(data):
            uid = data.get('user_id', 'default_user_id')
            gid = data.get('group_id', 'default_group_id')
            platform = data.get('platform', 'unknown')

            if data.get("detail_type")=="group_member_increase":
                Main._add_record_enter(self.counter["GroupEnter"], platform, uid, gid)
            
            date = datetime.now().strftime("%y%m%d")
            Main._add_record(self.counter["notices"], platform, date, uid, gid)

        @sdk.adapter.on("request")
        async def on_request(data):
            platform = data.get('platform', 'unknown')
            date = datetime.now().strftime("%y%m%d")
            uid = data.get('user_id', 'default_user_id')
            gid = data.get('group_id', 'default_group_id')
            Main._add_record(self.counter["requests"], platform, date, uid, gid)

    # 三、面向外部的统计
    # 1.数据总览
    def total(self):
        return {
            "messages": self.counter["messages"]["_total"],
            "notices": self.counter["notices"]["_total"],
            "requests": self.counter["requests"]["_total"],
            "all": self.counter["messages"]["_total"] + self.counter["notices"]["_total"] + self.counter["requests"]["_total"]
        }
    
    def platform_total(self):
        result = {'messages': {}, 'notices': {}, 'requests': {}}
        for cat in ['messages', 'notices', 'requests']:
            platforms = self.counter[cat]
            for p, pdata in platforms.items():
                if p!="_total":
                    result[cat][p] = pdata["_total"]
        return result

    # 2.数据筛选
    def by_platform(self, platform):
        if not platform:
            raise ValueError("如果不填platfrom，请使用platform_total()")
        result = {'messages': 0, 'notices': 0, 'requests': 0}
        for cat in ['messages', 'notices', 'requests']:
            platforms = self.counter[cat]
            if platform in platforms:
                result[cat] = platforms[platform]['_total']
        return result
    
    @staticmethod
    def _get_date_range(days=None, start_date=None, end_date=None):
        today = datetime.now().date()
        if days is not None:
            start = today - timedelta(days=days - 1)
            end = today
        elif start_date and end_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            start = end = today
        return start, end

    def by_time(self,
                platform, 
                uid=None, 
                gid=None, 
                days=None, 
                start=None, 
                end=None,
                reply="number"):
        """
        按时间维度查询指定平台的消息统计数据
            platform (str): 平台名称，必填。
            uid (str, optional): 用户ID。指定后返回该用户的个人消息数
            gid (str, optional): 群组ID。指定后返回该群组的消息总数
            days (int, optional): 查询最近N天的数据（包含今天），优先级高于 start/end
            start (str, optional): 起始日期，格式: 'YYYY-MM-DD'，需与 end 同时使用
            end (str, optional): 结束日期，格式: 'YYYY-MM-DD'，需与 start 同时使用
        ***
        Returns a dict.
            
        Examples:
            最近5天的平台总数据
            by_time("yunhu", days=5)
            
            指定日期范围
            by_time("yunhu", start='1999-06-20', end='1999-06-30')
            
            指定用户最近5天的数据
            by_time("yunhu", uid='1999', days=5)
            
            指定群最近5天的数据
            by_time("yunhu", gid='505', days=5)
            
            查询指定群中某个用户的数据
            by_time("yunhu", uid='1999', gid='1999', days=7)
            
            不传时间参数，默认查询今天
            by_time("yunhu")

            返回示例
            {'990701': 5, }
        
        Note:
            - days、start/end 三选一，优先级: days > start/end > 默认今天
            - uid 和 gid 可单独使用，也可组合使用（查询用户在指定群的数据）
            - 日期返回格式为 'YYMMDD'（如 '260701' 表示 2026-07-01）
            - 如果某天没有数据，对应日期返回 0
            
        """
        if platform is None:
            raise ValueError("platform是必填项")
        
        start, end = self._get_date_range(days, start, end)
        dates = [(start + timedelta(days=i)).strftime("%y%m%d") 
                for i in range((end - start).days + 1)]
        
        # 获取平台数据
        platform_stat = self.counter['messages'].get(platform)
        if not platform_stat:
            return {d: 0 for d in dates}
        
        result = {}
        for day in dates:
            daliy_stat = platform_stat.get(day)
            if not daliy_stat:
                result[day] = {} if (reply == "dict") else 0
                continue
            
            if gid:
                source = daliy_stat['groups'].get(gid, {})
            elif uid:
                source = daliy_stat['users'].get(uid, {})
            else:
                source = daliy_stat

            if reply == "dict":
                result[day] = source
            else:
                if gid and uid:
                    result[day] = source.get(uid, 0)
                else:
                    result[day] = source.get("_total", 0)
        
        return result

    def get_1day(self, platform, uid=None, gid=None):
        """获取当天消息量"""
        return self.by_time(platform, uid, gid, days=1)

    def get_7days(self, platform, uid=None, gid=None):
        """获取近7天消息量"""
        return self.by_time(platform, uid, gid, days=7)

    def get_30days(self, platform, uid=None, gid=None):
        """获取近30天消息量"""
        return self.by_time(platform, uid, gid, days=30)

    def get_summary(self, platform, uid=None, gid=None, reply="counts"):
        if reply=="counts":
            today_data = self.by_time(platform, uid, gid, days=1)
            week_data = self.by_time(platform, uid, gid, days=7)
            month_data = self.by_time(platform, uid, gid, days=30)
            return {
                'totals':{
                    'today': sum(today_data.values()),
                    'last_7_days': sum(week_data.values()),
                    'last_30_days': sum(month_data.values())
                },
                'counts': {
                    'today': today_data,
                    'last_7_days': week_data,
                    'last_30_days': month_data
                }
            }
        elif reply=="details":
            return {
                'details': {
                    'today': self.by_time(platform, uid, gid, days=1, reply="dict"),
                    'last_7_days': self.by_time(platform, uid, gid, days=7, reply="dict"),
                    'last_30_days': self.by_time(platform, uid, gid, days=30, reply="dict")
                }
            }

    def get_enter(self, platform, uid, gid):
        p = self.counter.get("GroupEnter",{}).get(platform, {})
        return p.get(gid,{}).get(uid, 0)

    def reset(self):
        self.counter = self._default_counter()
        Main._save_counter()
        self.logger.info("统计数据已重置")