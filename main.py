import base64
import datetime
import json
import logging
from logging import handlers
import os
import random
import sys
import time
from urllib.parse import urlencode
import requests
from lxml import etree
from pyquery import PyQuery as pq
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from urllib3 import encode_multipart_formdata

# 登录 URL
LOGIN_URL = "https://api.sanfengyun.com/www/login.php"
# 查看用户信息的 URL
USER_URL = "https://api.sanfengyun.com/www/user.php"
# 检测延期和执行延期操作的 URL
DELAY_URL = "https://api.sanfengyun.com/www/renew.php"
# 发表评论的 URL
DELIVER_COMMENT_URL = "http://www.adminxy.com/request/request.asp"
# 获取评论 URL
GET_COMMENT_URL = "http://www.adminxy.com/showidc-4335.asp"

# 当前 py 文件的目录
filepath = os.path.dirname(os.path.realpath(sys.argv[0]))
# 用户信息
user_info = None

# 三丰云请求头
SAN_HEADER = {
    "authority": "api.sanfengyun.com",
    "method": "POST",
    "scheme": "https",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "zh-CN,zh;q=0.9",
    "origin": "https://www.sanfengyun.com",
    "referer": "https://www.sanfengyun.com/",
    "sec-ch-ua": 'Google Chrome";v="89", "Chromium";v="89", ";Not A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36",
}


# 检测是否可以免费延期
def check_free_delay():
    check_data = {
        "cmd": "check_free_delay",
        "ptype": "vps"
    }
    # 请求头
    SAN_HEADER['path'] = "/www/renew.php"
    SAN_HEADER['accept'] = "*/*"
    SAN_HEADER['content-type'] = "application/x-www-form-urlencoded"
    try:
        resp = requests.post(url=DELAY_URL, headers=SAN_HEADER, data=check_data).json()
        logging.info("***检测延期，%s ***" % resp)
        if resp['msg']['delay_enable'] == 1:
            logging.info('***已经到了延期时间，可以进行免费延期操作***')
            return True
        logging.info('***未到延期时间，即将退出***')
        return False
    except Exception:
        logging.info('***检测延期时发生异常，终止操作***')
        return False


# 初始化日志模块
def init_logger():
    logger = logging.getLogger()
    format_str = logging.Formatter('%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s: %(message)s')
    logger.setLevel(logging.INFO)
    sh = logging.StreamHandler()
    sh.setFormatter(format_str)
    th = handlers.TimedRotatingFileHandler(filename='auto-delay.log', when='D', interval=1, backupCount=0,
                                           encoding='utf-8')
    th.suffix = "%Y%m%d_%H%M%S.log"
    th.setFormatter(format_str)
    logger.addHandler(sh)
    logger.addHandler(th)
    logging.info('***日志模块初始化***')

    # logging.debug('debug message')
    # logging.info('info message')
    # logging.warning('warning message')
    # logging.error('error message')
    # logging.critical('critical message')


# 检测用户当前登录 IP
def get_user_ip_addr():
    user_data = {
        "cmd": "user_log",
        "keyword": "",
        "count": 10,
        "page": 1
    }
    # 请求头
    SAN_HEADER['path'] = "/www/user.php"
    SAN_HEADER['accept'] = "*/*"
    SAN_HEADER['content-type'] = "application/x-www-form-urlencoded"
    try:
        resp = requests.post(url=USER_URL, headers=SAN_HEADER, data=user_data).json()
        if resp['msg']['content'][0]['ip_addr']:
            logging.info("***获取到用户登录地址，%s ***" % resp['msg']['content'][0]['ip_addr'])
            return
        logging.info('***未获取到用户登录地址***')
    except Exception:
        logging.info('***获取用户登录地址发生异常***')


# 载入用户信息 JSON
def load_user_info():
    try:
        filename = "userinfo.json"
        if len(sys.argv) > 1:
            filename = sys.argv[1]
        with open(filepath + "/" + filename, "r") as f:
            logging.info('***载入用户JSON：%s 成功***' % filename)
            return json.load(f)
    except Exception:
        logging.info('***载入用户JSON异常终止***')
        return None


# 登录：返回 COOKIE
def do_login(data):
    # 请求头
    SAN_HEADER['path'] = "/www/login.php"
    SAN_HEADER['accept'] = "application/json, text/javascript, */*; q=0.01"
    SAN_HEADER['content-type'] = "application/x-www-form-urlencoded; charset=UTF-8"
    data['cmd'] = "login"
    try:
        resp = requests.post(url=LOGIN_URL, headers=SAN_HEADER, data=data)
        resp_json = resp.json()
        if resp_json['response'] != '200':
            logging.info("***登录失败，原因：%s" % resp_json['msg'])
            return None
        cookies = {}
        for key, value in resp.cookies.items():
            cookies[key] = value
        logging.info("***登录成功，获取session_id成功：%s" % cookies)
        return cookies
    except Exception:
        logging.info("***登录时发生异常，登录失败")
        return None


# 在 【主机评测】网发表评论
def deliver_comment():
    # 随机生成评论内容次数，失败超过该次数 发表评论失败
    repeat_times = 3
    # 评论表单数据
    comment_data = {
        "cname": "匿名",  # 昵称
        "csubject": "点评：三丰云",  # 标题
        "p1": 5,  # 速度
        "p2": 5,  # 服务
        "p3": 5,  # 性价比
        "p4": 5,  # 安全性
        "ccontent": "",  # 评论内容
        "belong": 4335,
        "button": " 提交 "
    }
    if user_info['cname']:
        comment_data['cname'] = user_info['cname']
    # 请求头
    post_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "http://www.adminxy.com",
        "Referer": "http://www.adminxy.com/showidc-4335.asp",
        "Host": "www.adminxy.com",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36"
    }
    try:
        comment = get_a_comment()
        while not comment and repeat_times > 0:
            logging.info("***生成 COMMENT 失败，重新生成***")
            comment = get_a_comment()
            repeat_times = repeat_times - 1
        if not comment and repeat_times == 0:
            # 评论失败
            logging.info("***评论失败，生成 COMMENT 超限***")
            return False
        comment_data['ccontent'] = comment
        comment_data = urlencode(comment_data, encoding='gb2312')
        resp = requests.post(url=DELIVER_COMMENT_URL, headers=post_headers, data=comment_data)
        resp.encoding = "gb2312"
        result_dom = etree.HTML(resp.text)
        # print(resp.text)
        result = result_dom.xpath("/html/body/table/tr[1]/td/text()")
        logging.info("--- %s ---" % result)
        # result = result_dom.xpath("/html/body/script/text()")
        if result and result[0].find('恭喜您，点评成功！') != -1:
            logging.info("***评论成功***")
            # 评论成功
            return True
        return False
    except Exception:
        # 评论失败
        logging.info("***评论失败，出现未知异常***")
        return False


# 获取一条评论
def get_a_comment():
    # 请求头
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Host": "www.adminxy.com",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36"
    }
    try:
        resp = requests.get(url=GET_COMMENT_URL, headers=headers)
        resp.encoding = "gb2312"
        result_dom = pq(resp.text)
        comments_tr = result_dom('body > div.twidth > div.pagebodyshow > div.mainbodyshow > div:nth-child(5) > div.wrapper > div.mm > table > tr:nth-child(1) > td > table > tr:nth-child(4n+3)')
        comments = []
        for item in comments_tr.items():
            comments.append(item.text())
        comment1 = random.choice(comments)
        comment2 = random.choice(comments)
        comment = comment1[0:int(len(comment1) / 2)] + comment2[int(len(comment2) / 2):] + "！三丰云就是牛叉！！！"
        logging.info("***生成评论成功***")
        return comment
    except Exception:
        logging.info("***生成评论失败，出现未知异常***")
        return None


# 获取一张评论截图
def get_comment_screenshot():
    browser = None
    try:
        if not os.path.exists("/usr/bin/chromedriver"):
            logging.info("*** /usr/bin/chromedriver 不存在 ***")
            return None
        option = ChromeOptions()
        # 开启无头模式
        option.add_argument('--no-sandbox')
        option.add_argument('--headless')  # 无头参数
        option.add_argument('--disable-gpu')
        browser = webdriver.Chrome(options=option, executable_path=r"/usr/bin/chromedriver")
        browser.get(url=GET_COMMENT_URL)
        time.sleep(0.5)
        scroll_width = 1200
        scroll_height = 400
        browser.set_window_size(scroll_width, scroll_height)
        comments = browser.find_element_by_xpath(
            "/html/body/div[2]/div[2]/div[1]/div[3]/div[4]/div[3]/table/tbody/tr[1]/td/table/tbody")

        comments = comments.find_elements_by_css_selector("tr:nth-child(4n+0)")
        # 滑动滚动条到某个指定的元素
        image_name = datetime.datetime.now().strftime('%Y-%m-%d-%H:%M:%S') + ".png"
        js4 = "arguments[0].scrollIntoView(false);"
        if user_info['cname'] and user_info['cname'] != '匿名':
            flag = user_info['cname']
        else:
            flag = user_info['area']
        for comment in comments:
            if comment.text.find(flag) != -1:
                # print("*** " + comment.text)
                logging.info("***找到截图节点所在位置***")
                browser.execute_script(js4, comment)
                time.sleep(0.5)
                browser.save_screenshot(filepath + "/screenshot/" + image_name)
                logging.info("***截图成功，%s***" % image_name)
                time.sleep(0.5)
                return image_name
        logging.info("***截图失败***")
        return None
    except Exception:
        logging.info("***截图失败，出现未知异常***")
        return None
    finally:
        if browser:
            browser.close()
            browser.quit()


# 延期操作
def free_delay_add(filename):
    files = {
        'cmd': (None, "free_delay_add"),
        'ptype': (None, "vps"),
        'url': (None, "http://www.adminxy.com/showidc-4335.asp"),
        'yanqi_img': (filename, open(filepath + "/screenshot/" + filename, 'rb').read(), 'image/png')
    }
    # 自定义表单 boundary 并编码
    boundary = '----WebKitFormBoundarykYZ25McvRHOtaBYE'
    data = encode_multipart_formdata(files, boundary=boundary)

    # 请求头
    SAN_HEADER['path'] = "/www/renew.php"
    SAN_HEADER['accept'] = "*/*"
    SAN_HEADER['content-type'] = "multipart/form-data; boundary=----WebKitFormBoundarykYZ25McvRHOtaBYE"
    try:
        resp = requests.post(url=DELAY_URL, headers=SAN_HEADER, data=data[0]).json()
        logging.info("***延期请求响应成功，%s ***" % resp)
        if resp['response'] != '200':
            logging.info('***延期失败，原因：%s ***' % resp['msg'])
            return False
        logging.info('***%s***' % resp['msg'])
        return True
    except Exception:
        logging.info('***延期时异常，终止延期***')
        return False


def main():
    global user_info
    user_info = load_user_info()
    cookies = do_login({'id_mobile': user_info['phone'], 'password': user_info['password']})
    # cookies = {'session_id': '1616816974450738525'}
    cookie = ""
    # 构造 Cookie
    for key in cookies.keys():
        cookie = cookie + f"{key}={cookies[key]};"
    SAN_HEADER["cookie"] = cookie
    get_user_ip_addr()

    flag = check_free_delay()
    if not flag:
        logging.info("***未到延期时间，退出***")
        return
    # 发表评论重试次数
    times = 0
    logging.info("***到达延期时间，即将发表评论***")
    flag = deliver_comment()
    while not flag and times > 0:
        logging.info("***评论失败，重新进行评论***")
        flag = deliver_comment()
        times = times - 1
    if not flag and times == 0:
        # 评论失败
        logging.info("***评论失败，发表评论重试次数超限***")
        return
    image_name = get_comment_screenshot()
    if not image_name:
        logging.info("***评论截图失败，退出***")
        return

    # image_name = "2021-03-27-11:51:18.png"
    logging.info("***获取评论截图成功，开始进行免费延期操作 ***")
    free_delay_add(image_name)


if __name__ == '__main__':
    init_logger()
    main()
