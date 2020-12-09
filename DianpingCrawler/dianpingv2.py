#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
__author__ = 'AJay'
__mtime__ = '2019/3/21 0021'

"""
import datetime
from json import encoder
import random
import re
import time
import redis
import json

import requests
from lxml import etree
from requests.api import post

# 保存当前商店评论页的url，方便继续爬
Break_Point = "resume_break_point"
# 保存所有商店url
Shop_Point = "shop_break_point"


class DianpingComment:
    font_size = 14
    start_y = 23

    def __init__(self, keyword, cookies, delay=7):
        redis_host = "127.0.0.1"
        redis_port = 6379
        redis_pass = None

        if redis_pass:
            pool = redis.ConnectionPool(
                host=redis_host, port=redis_port, password=redis_pass, decode_responses=True)
        else:
            pool = redis.ConnectionPool(
                host=redis_host, port=redis_port, decode_responses=True)
        self.r = redis.Redis(connection_pool=pool)

        self.shop_name = None
        self.shop_id = None
        self.keyword = keyword
        self._delay = delay
        self.font_dict = {}
        self._cookies = self._format_cookies(cookies)
        self._css_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
        }
        self._default_headers = {
            'Connection': 'keep-alive',
            'Host': 'www.dianping.com',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36',
        }
        self._cur_key_url = 'http://www.dianping.com/search/keyword/2/0_{}'.format(
            keyword)

        if self.r.llen(Shop_Point) > 0:
            self._cur_shop_url = self.r.lpop(Shop_Point)
        else:
            self._cur_shop_url = ''

    def _delay_func(self):
        delay_time = random.randint(
            (self._delay - 2) * 10, (self._delay + 2) * 10) * 0.1
        print('睡一会', delay_time)
        time.sleep(delay_time)

    def _format_cookies(self, cookies):
        cookies = {cookie.split('=')[0]: cookie.split('=')[1]
                   for cookie in cookies.replace(' ', '').split(';')}
        return cookies

    def _get_css_link(self, url):
        """
            请求评论首页，获取css样式文件
        """
        res = requests.get(self._cur_request_css_url,
                           headers=self._default_headers, cookies=self._cookies)
        html = res.text
        # print('首页源码',self._cur_request_css_url, html)
        # css_link = re.search(r'<link re.*?css.*?href="(.*?svgtextcss.*?)">', html)
        css_link = re.findall(
            r'<link rel="stylesheet" type="text/css" href="//s3plus.meituan.net/v1/(.*?)">', html)
        assert css_link, "Need validation: {}".format(self._cur_request_css_url)
        css_link = 'http://s3plus.meituan.net/v1/' + css_link[0]
        print('css链接', css_link)
        return css_link

    def _get_font_dict_by_offset(self, url):
        """
            获取坐标偏移的文字字典, 会有最少两种形式的svg文件（目前只遇到两种）
        """
        res = requests.get(url, timeout=60)
        html = res.text
        font_dict = {}
        y_list = re.findall(r'd="M0 (\d+?) ', html)
        if y_list:
            font_list = re.findall(r'<textPath .*?>(.*?)<', html)
            for i, string in enumerate(font_list):
                y_offset = self.start_y - int(y_list[i])

                sub_font_dict = {}
                for j, font in enumerate(string):
                    x_offset = -j * self.font_size
                    sub_font_dict[x_offset] = font

                font_dict[y_offset] = sub_font_dict

        else:
            font_list = re.findall(r'<text.*?y="(.*?)">(.*?)<', html)

            for y, string in font_list:
                y_offset = self.start_y - int(y)
                sub_font_dict = {}
                for j, font in enumerate(string):
                    x_offset = -j * self.font_size
                    sub_font_dict[x_offset] = font

                font_dict[y_offset] = sub_font_dict
        print('字体字典', font_dict)
        return font_dict

    def _get_font_dict(self, url):
        """
            获取css样式对应文字的字典
        """
        print('解析svg成字典的css', url)
        res = requests.get(url, headers=self._css_headers,
                           cookies=self._cookies, timeout=60)
        html = res.text

        background_image_link = re.findall(
            r'background-image: url\((.*?)\);', html)
        # print('带有svg的链接', background_image_link)
        assert background_image_link
        # background_image_link = 'http:' + background_image_link[0]
        # html = re.sub(r'span.*?\}', '', html)
        # group_offset_list = re.findall(r'\.([a-zA-Z0-9]{5,6}).*?round:(.*?)px (.*?)px;', html)  # css中的类
        # print('css中class对应坐标', group_offset_list)
        # font_dict_by_offset = self._get_font_dict_by_offset(background_image_link)  # svg得到这里面对应成字典
        # print('解析svg成字典', font_dict_by_offset)

        # 原版只解析一个svg文件，少了很多字，尝试循环处理
        html = re.sub(r'span.*?\}', '', html)
        # group_offset_list = re.findall(r'\.([a-zA-Z0-9]{5,6}).*?round:(.*?)px (.*?)px;', html)  # css中的类
        group_offset_list = re.findall(
            r'\.([a-zA-Z0-9]{5,6}){.*?round:(.*?)px (.*?)px;', html)  # css中的类
        # print('css中class对应坐标', group_offset_list)
        font_dict_by_offset = {}
        for i in background_image_link:
            link = 'http:' + i
            font_dict_by_offset.update(
                self._get_font_dict_by_offset(link))  # svg得到这里面对应成字典
        print('解析svg成字典', font_dict_by_offset)

        for class_name, x_offset, y_offset in group_offset_list:
            y_offset = y_offset.replace('.0', '')
            x_offset = x_offset.replace('.0', '')
            self.r.hset("font", class_name, "{},{}".format(y_offset, x_offset))
            # print(y_offset,x_offset)
            if font_dict_by_offset.get(int(y_offset)):
                self.font_dict[class_name] = font_dict_by_offset[int(
                    y_offset)][int(x_offset)]
        # special treat
        # self.font_dict['zltswc']='工'
        # self.font_dict['zuc30h']='堆'
        # self.font_dict['xl06i'] = '丁'
        return self.font_dict

    def _data_pipeline(self, data):
        """
            处理数据
        """
        if self.r.llen(self.shop_id) > 0 and data is not None:
            self.r.rpushx(self.shop_id, json.dumps(data))
        else:
            self.r.rpush(self.shop_id, json.dumps(data))
        print('最终数据:', data)

    def _parse_shop_name(self, doc):
        shop_name = doc.xpath(
            './/h1[@class="shop-name"]/text()')[0].strip('\n\r \t')
        self.shop_name = shop_name

    def _parse_comment_page(self, doc):
        """
            解析评论页并提取数据
        """
        for li in doc.xpath('//*[@class="reviews-items"]/ul/li'):

            name = li.xpath('.//a[@class="name"]/text()')[0].strip('\n\r \t')
            try:
                star = li.xpath(
                    './/span[contains(./@class, "sml-str")]/@class')[0]
                star = re.findall(r'sml-rank-stars sml-str(.*?) star', star)[0]
            except IndexError:
                star = 0
            time = li.xpath(
                './/span[@class="time"]/text()')[0].strip('\n\r \t')
            pics = []

            if li.xpath('.//*[@class="review-pictures"]/ul/li'):
                for pic in li.xpath('.//*[@class="review-pictures"]/ul/li'):
                    print(pic.xpath('.//a/@href'))
                    pics.append(pic.xpath('.//a/img/@data-big')[0])
            comment = ''.join(
                li.xpath('.//div[@class="review-words Hide"]/text()')).strip('\n\r \t')
            if not comment:
                comment = ''.join(
                    li.xpath('.//div[@class="review-words"]/text()')).strip('\n\r \t')

            data = {
                'name': name,
                'comment': comment,
                'star': star,
                'pic': pics,
                'time': time,
                'shopname': self.shop_name
            }
            self._data_pipeline(data)

    def _get_conment_page(self):  # 获得评论内容
        """
            请求评论页，并将<span></span>样式替换成文字
        """
        while self._cur_request_url:
            self._delay_func()
            print('[{now_time}] {msg}'.format(
                now_time=datetime.datetime.now(), msg=self._cur_request_url))
            res = requests.get(
                self._cur_request_url, headers=self._default_headers, cookies=self._cookies)
            html = res.text
            class_set = set()
            for svgmtsi in re.findall(r'<svgmtsi class="([a-zA-Z0-9]{5,6})"></svgmtsi>', html):
                class_set.add(svgmtsi)
            for class_name in class_set:
                html = re.sub('<svgmtsi class="%s"></svgmtsi>' %
                              class_name, self._font_dict[class_name], html)
            doc = etree.HTML(html)
            if not self.shop_name:
                self._parse_shop_name(doc)
            self._parse_comment_page(doc)
            try:
                self._default_headers['Referer'] = self._cur_request_url
                postfix = doc.xpath('.//a[@class="NextPage"]/@href')
                if postfix:
                    postfix = postfix[0]
                    next_page_url = 'http://www.dianping.com{}'.format(postfix)
                    self.r.hset(Break_Point, self.shop_id, next_page_url)
                    self._cur_request_url = next_page_url
                else:
                    print("到底了")
                    self._cur_request_url = None
            except Exception as e:
                print("找不到下一页：{}".format(e))
                self._cur_request_url = None

    def _get_shop_url_list(self):
        """
        获取关键字所有店铺的url列表
        """
        shop_dict = {}
        self.r.delete("shop_list")
        while(self._cur_key_url):
            self._cur_key_url = self._cur_key_url.encode()
            res = requests.get(
                self._cur_key_url, headers=self._default_headers, cookies=self._cookies)
            html = res.text
            doc = etree.HTML(html)
            for li in doc.xpath('//*[@class="shop-list J_shop-list shop-all-list"]/ul/li'):
                url = li.xpath('.//a/@href')[0]
                name = li.xpath('.//h4/text()')[0]
                if self.keyword not in name:
                    continue
                print("增加店铺url：{}, {}".format(name, url))
                shop_dict = {"shop_name": name, "shop_url": url}
                self.r.rpush("shop_list", json.dumps(shop_dict))
            try:
                self._default_headers['Referer'] = self._cur_key_url
                next_page_url = doc.xpath('.//a[@class="next"]/@href')
                # assert next_page_url==[], "到底了，没有更多店铺了"
                if next_page_url:
                    self._cur_key_url = next_page_url[0]
                else:
                    print("到底了，没有更多店铺了")
                    self._cur_key_url = None
            except Exception as e:
                print("找不到下一页：{}".format(e))
                self._cur_key_url = None


    def run(self):
        self._get_shop_url_list()
        shop_dict = json.loads(self.r.lpop("shop_list"))
        shop_id = shop_dict.get("shop_url").split("shop/")[1]
        while shop_id:
            self.shop_id = shop_id
            self.shop_name = shop_dict.get("shop_name")
            if self.r.hexists(Break_Point, shop_id):
                self._cur_request_url = self.r.hget(Break_Point, shop_id)
            else:
                self._cur_request_url = 'http://www.dianping.com/shop/{}/review_all/p1'.format(
                    shop_id)
            self._cur_request_css_url = 'http://www.dianping.com/shop/{}/review_all'.format(
                    shop_id)
            try:
                self._css_link = self._get_css_link(self._cur_request_url)
                print('css 的连接', self._css_link)
                self._font_dict = self._get_font_dict(self._css_link)
                self._get_conment_page()
                shop_dict = json.loads(self.r.lpop("shop_list"))
                shop_id = shop_dict.get("shop_url").split("shop/")[1]
            except Exception as e:
                print("店铺切换问题：{}".format(e))
                self.r.lpush("shop_list", json.dumps(shop_dict))
                break


if __name__ == "__main__":
    # COOKIES = '_lxsdk_cuid=174140242ebc8-0124535e70043a-3323766-130980-174140242eb66; _lxsdk=174140242ebc8-0124535e70043a-3323766-130980-174140242eb66; _hc.v=53d8a52e-e1b1-6a40-2c87-43ec367dfa62.1598063527; s_ViewType=10; aburl=1; __utma=1.75733673.1599534050.1599534050.1599534050.1; __utmc=1; __utmz=1.1599534050.1.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none); ll=7fd06e815b796be3df069dec7836c3df; ua=13811275737; ctu=1d3cf8bd0ab16c6c5c01abe1c3d223d87bd8a6f54991c9bcdc83ab765dd6662c; Hm_lvt_602b80cf8079ae6591966cc70a3940e7=1606267108; cy=2; cye=beijing; fspop=test; dper=5b64bf52184d0e5b94eeeb89a15425d4d7357b949024d9f0e646db58d9a7c52e0a5b6e6d5374ffe42cad051ad226c2fa8f7de391361b8e93fd922661e84401c37881c9ad8e9d79854affc73074996df14713a3fb93c43e28ef95f41338694a4a; dplet=8b1f7019ac18e57d3d311adb49b49b2a; Hm_lpvt_602b80cf8079ae6591966cc70a3940e7=1607412780; _lxsdk_s=17640e3f3c6-5f-305-7a%7C%7C800'
    COOKIES = "_lxsdk_cuid=175a88be2f2c8-07dbb17c3f0c2f-163e6152-fa000-175a88be2f2c8; _lxsdk=175a88be2f2c8-07dbb17c3f0c2f-163e6152-fa000-175a88be2f2c8; _hc.v=eec61957-8eac-8682-502e-3a53a9f38674.1604850541; s_ViewType=10; Hm_lvt_602b80cf8079ae6591966cc70a3940e7=1604850542,1604850620; cy=2; cye=beijing; ll=7fd06e815b796be3df069dec7836c3df; ua=13811275737; ctu=1d3cf8bd0ab16c6c5c01abe1c3d223d84cde85741f735cebe59c31bbe3281ea7; fspop=test; lgtoken=00a61ecb0-3af2-4d9e-9a28-ad356131a5df; dper=dfb2ffc045f604696e647765bec04a9a4a43abb55c5098856b0037b58487c18fb4ac7f592c85b8436856667f6b8e29cf838bb1c4ad0843a90a7d11ab0a02d9ea2726102e70b8019ba7d8e1a60afc3d94df5ebd43c6e60b40a5c7beee1796e5bb; dplet=7d577402984f2fc65f3a089403dc7eef; Hm_lpvt_602b80cf8079ae6591966cc70a3940e7=1607436587; _lxsdk_s=17642adcb2d-056-6fb-b21%7C%7C354"

    dp = DianpingComment('哈根达斯', cookies=COOKIES)
    dp.run()
