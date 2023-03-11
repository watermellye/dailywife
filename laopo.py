from hoshino import Service, priv, config
from hoshino.typing import CQEvent, HoshinoBot
from hoshino import get_bot, aiorequests
import httpx
import hashlib
import base64
import os
import json
import datetime
from random import choice
from typing import List
from asyncio import Lock
from nonebot import on_startup

max_wife_cnt = 3  # 一天可以摇几次
max_charge_cnt = 1  # 一天可以冲几次
admin_qqid_int = 491673070

sv = Service(
    name="今日老婆",  # 功能名
    visible=True,  # 可见性
    enable_on_default=True,  # 默认启用
    bundle="娱乐",  # 分组归类
    help_="发送【今日老婆】随机抓取群友作为老婆",  # 帮助说明
)


async def downloadUrl(url: str) -> bytes:
    try:
        resp = await aiorequests.get(url, timeout=3)
        assert resp.status_code == 200, f'status_code={resp.status_code}'
    except Exception as e:
        return None
    else:
        return await resp.content


async def getAvatarBytes(user_id: int) -> bytes:
    url = f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s="
    return await downloadUrl(f'{url}160')
    # data = await downloadUrl(f'{url}160')  # 100 160 640
    # if data is None or hashlib.md5(data).hexdigest() == "acef72340ac0e914090bd35799f5594e":
    #     data = await downloadUrl(f'{url}100')
    # return data


async def getAvatarInfo(group_id: int, member_id: int) -> str:
    bot = get_bot()
    member_info = await bot.get_group_member_info(group_id=group_id, user_id=member_id)
    outp = f'{member_info["card"] or member_info["nickname"]}({member_id})'
    data = await getAvatarBytes(member_id)
    if data is not None:
        avatar_b64 = 'base64://' + base64.b64encode(data).decode()
        outp = f'[CQ:image,file={avatar_b64}]\n{outp}'
    return outp


curpath = os.path.dirname(__file__)
member_qqid_cache = {}
'''
{
    "group_id_str": {
        "member_qqid_list": [],
        "cache_time": "2022-12-13"
    }
}
'''


async def getMemberQQidList(group_id: int):
    today = str(datetime.date.today())
    group_id_str = str(group_id)
    global member_qqid_cache
    if member_qqid_cache.get(group_id_str, {}).get("cache_time", "") == today:
        return member_qqid_cache[group_id_str]["member_qqid_list"]

    bot = get_bot()
    member_qqid_list = [member['user_id'] for member in (await bot.get_group_member_list(group_id=group_id))]
    member_qqid_cache[group_id_str] = {"member_qqid_list": member_qqid_list, "cache_time": today}
    return member_qqid_list


def saveGroupConfig(group_id, config) -> None:
    config_file = os.path.join(curpath, f'config/{group_id}.json')
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def loadGroupConfig(group_id) -> dict:
    config_file = os.path.join(curpath, f'config/{group_id}.json')
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except:
        config = {}
    today = str(datetime.date.today())
    for day in list(config):
        if day != today:
            del config[day]
    if today not in config:
        config[today] = {}
    saveGroupConfig(group_id, config)
    return config


lck = Lock()


@sv.on_fullmatch(('摇老婆充值', '充值老婆', '老婆充值', '冲老婆'))
async def charge(bot: HoshinoBot, ev: CQEvent):
    async with lck:
        global max_wife_cnt, max_charge_cnt, admin_qqid_int
        group_id = ev.group_id
        user_id = ev.user_id
        today = str(datetime.date.today())
        config = loadGroupConfig(group_id)
        today_config = config[today]

        if user_id == admin_qqid_int:
            return

        user_id_str = str(user_id)
        if user_id_str not in today_config:
            await bot.finish(ev, "你今天还没摇过老婆，不执行充值", at_sender=True)
        charge_cnt = today_config[user_id_str].get("charge_cnt", 0)
        if charge_cnt >= max_charge_cnt:
            await bot.finish(ev, "你今天已经申请过氪金，不要太贪心哦", at_sender=True)
        today_config[user_id_str]["charge_cnt"] = charge_cnt + 1
        today_config[user_id_str]["wife_cnt"] = min(today_config[user_id_str]["wife_cnt"] - max_wife_cnt, 0)
        saveGroupConfig(group_id, config)
        await bot.finish(ev, f'氪金成功\n*你今天还可以使用{max_wife_cnt - today_config[user_id_str]["wife_cnt"]}次“摇老婆”', at_sender=True)


@sv.on_fullmatch(('今日老婆', '查询老婆', '查老婆'))
async def findWife(bot: HoshinoBot, ev: CQEvent):
    async with lck:
        get = False
        global max_wife_cnt, max_charge_cnt, admin_qqid_int
        group_id = ev.group_id
        user_id = ev.user_id
        today = str(datetime.date.today())
        title = "老婆"
        config = loadGroupConfig(group_id)
        today_config = config[today]
        user_id_str = str(user_id)
        if user_id_str not in today_config:
            get = True
        else:
            wife_qqid_int = today_config[user_id_str]["wife_qqid_int"]
            wife_cnt = today_config[user_id_str]["wife_cnt"]
            if wife_qqid_int is None:
                if wife_cnt <= max_wife_cnt:
                    await bot.send(ev, f'你目前是单身狗\n*你今天还可以使用{max_wife_cnt - wife_cnt}次“摇老婆”', at_sender=True)
                else:
                    await bot.send(ev, f'你今天是单身狗', at_sender=True)
            else:
                if wife_cnt > max_wife_cnt and wife_qqid_int == admin_qqid_int:
                    title = "老公"

                avatar_msg = f'你今天的群友{title}是：{await getAvatarInfo(group_id, wife_qqid_int)}'
                charge_cnt = today_config[user_id_str].get("charge_cnt", 0)

                if max_wife_cnt - wife_cnt > 0:
                    cnt_msg = f'*你今天还可以使用{max_wife_cnt - wife_cnt}次“摇老婆”'
                else:
                    if charge_cnt < max_charge_cnt:
                        cnt_msg = f'*你今天还可以使用{max_charge_cnt - charge_cnt}次“摇老婆充值”'
                    else:
                        #cnt_msg = f'*你今天不能再摇老婆了哦'
                        cnt_msg = ""
                await bot.send(ev, f'{avatar_msg}\n{cnt_msg}', at_sender=True)

    if get:
        await dailyWife(bot, ev)


@sv.on_fullmatch(('找老婆', '摇老婆', '抽老婆'))
async def dailyWife(bot: HoshinoBot, ev: CQEvent):
    async with lck:
        global max_wife_cnt, max_charge_cnt, admin_qqid_int
        group_id = ev.group_id
        user_id = ev.user_id
        bot_id = ev.self_id
        today = str(datetime.date.today())
        title = "老婆"
        config = loadGroupConfig(group_id)
        '''
        {
            "2022-12-13": {
                "husband_qqid_str" : {
                    "wife_qqid_int" : 123456789,
                    "wife_cnt": 0
                }
            }
        }
        '''
        today_config = config[today]  # 对today_config内的元素进行修改会反应到config上

        user_id_str = str(user_id)
        if user_id_str not in today_config:
            today_config[user_id_str] = {"wife_qqid_int": None, "wife_cnt": 0}

        wife_cnt = today_config[user_id_str]["wife_cnt"]
        if wife_cnt >= max_wife_cnt and user_id != admin_qqid_int:
            if wife_cnt >= max_wife_cnt + 3:
                return
            msg = []

            if wife_cnt == max_wife_cnt:
                msg.append(f'你今天已经摇了{wife_cnt}次{title}了！你的{title}被bot收回了')
                today_config[user_id_str]["wife_qqid_int"] = None

            if admin_qqid_int in (await getMemberQQidList(group_id)):
                today_config[user_id_str]["wife_qqid_int"] = admin_qqid_int
                msg.append(f'你今天的群友老公是：{await getAvatarInfo(group_id, admin_qqid_int)}')
            else:
                msg.append(f'你今天是单身狗')

            today_config[user_id_str]["wife_cnt"] = wife_cnt + 1

            await bot.send(ev, '\n'.join(msg), at_sender=True)
        else:
            member_qqid_list = await getMemberQQidList(group_id)
            cannot_choose_qqid_list = [bot_id, user_id]
            for husband_qqid_str in today_config:
                wife_qqid_int = today_config[husband_qqid_str]["wife_qqid_int"]
                if wife_qqid_int is not None:
                    cannot_choose_qqid_list.append(wife_qqid_int)
            choose_qqid_list = list(set(member_qqid_list) - set(cannot_choose_qqid_list))
            if len(choose_qqid_list) == 0:
                wife_qqid_int = today_config[user_id_str]["wife_qqid_int"]
                if wife_qqid_int is None:
                    await bot.send(ev, "今天群友都已经结伴啦，你是单身狗", at_sender=True)
                else:
                    await bot.send(ev, f'今天群友都已经结伴啦，不能再换{title}啦！\n你今天的群友{title}是：{await getAvatarInfo(group_id, wife_qqid_int)}', at_sender=True)
            else:
                wife_qqid_int = choice(choose_qqid_list)
                today_config[user_id_str]["wife_qqid_int"] = wife_qqid_int
                wife_cnt = today_config[user_id_str]["wife_cnt"] + 1
                today_config[user_id_str]["wife_cnt"] = wife_cnt

                avatar_msg = f'你今天的群友{title}是：{await getAvatarInfo(group_id, wife_qqid_int)}'
                charge_cnt = today_config[user_id_str].get("charge_cnt", 0)

                if max_wife_cnt - wife_cnt > 0:
                    cnt_msg = f'*你今天还可以使用{max_wife_cnt - wife_cnt}次“摇老婆”'
                else:
                    if charge_cnt < max_charge_cnt:
                        cnt_msg = f'*你今天还可以使用{max_charge_cnt - charge_cnt}次“摇老婆充值”'
                    else:
                        cnt_msg = f'*你今天不能再摇老婆了哦'
                await bot.send(ev, f'{avatar_msg}\n{cnt_msg}', at_sender=True)

        saveGroupConfig(group_id, config)
