#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
__author__ = 'AJay'
__mtime__ = '2019/3/21 0021'

"""
import datetime
import random
import re
import time
import redis
import json

import requests
from lxml import etree


Break_Point= "resume_break_point"

class DianpingComment:
    font_size = 14
    start_y = 23

    def __init__(self, shop_id, cookies, delay=7):
        redis_host = "127.0.0.1"
        redis_port = 6379
        redis_pass = None

        if redis_pass:
            pool = redis.ConnectionPool(host=redis_host, port=redis_port, password=redis_pass, decode_responses=True)
        else:
            pool = redis.ConnectionPool(host=redis_host, port=redis_port, decode_responses=True)
        self.r = redis.Redis(connection_pool=pool)

        self.shop_name = None
        self.shop_id = shop_id
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
        
        if self.r.hexists(Break_Point, shop_id):
            self._cur_request_url = self.r.hget(Break_Point, shop_id)
        else:
            self._cur_request_url = 'http://www.dianping.com/shop/{}/review_all/p1'.format(shop_id)
        #self._cur_request_css_url = 'http://www.dianping.com/shop/{}/'.format(shop_id)
        self._cur_request_css_url = 'http://www.dianping.com/shop/{}/review_all'.format(shop_id)
        

    def _delay_func(self):
        delay_time = random.randint((self._delay - 2) * 10, (self._delay + 2) * 10) * 0.1
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
        res = requests.get(self._cur_request_css_url, headers=self._default_headers, cookies=self._cookies)
        html = res.text
        # print('首页源码',self._cur_request_css_url, html)
        # css_link = re.search(r'<link re.*?css.*?href="(.*?svgtextcss.*?)">', html)
        css_link = re.findall(r'<link rel="stylesheet" type="text/css" href="//s3plus.meituan.net/v1/(.*?)">', html)
        assert css_link, "Need validation"
        css_link = 'http://s3plus.meituan.net/v1/' + css_link[0]
        print('css链接',css_link)
        return css_link



    def _get_font_dict_by_offset(self, url):
        """
            获取坐标偏移的文字字典, 会有最少两种形式的svg文件（目前只遇到两种）
        """
        res = requests.get(url,timeout=60)
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
        print('字体字典',font_dict)
        return font_dict

    def _get_font_dict(self, url):
        """
            获取css样式对应文字的字典
        """
        print('解析svg成字典的css', url)
        res = requests.get(url, headers=self._css_headers,cookies=self._cookies,timeout=60)
        html = res.text

        background_image_link = re.findall(r'background-image: url\((.*?)\);', html)
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
        group_offset_list = re.findall(r'\.([a-zA-Z0-9]{5,6}).*?round:(.*?)px (.*?)px;', html)  # css中的类
        # print('css中class对应坐标', group_offset_list)
        font_dict_by_offset = {}
        for i in background_image_link:
            link = 'http:' + i
            font_dict_by_offset.update(self._get_font_dict_by_offset(link))  # svg得到这里面对应成字典
        print('解析svg成字典', font_dict_by_offset)


        for class_name, x_offset, y_offset in group_offset_list:
            y_offset = y_offset.replace('.0', '')
            x_offset = x_offset.replace('.0', '')
            self.r.hset("font", class_name, "{},{}".format(y_offset,x_offset))
            # print(y_offset,x_offset)
            if font_dict_by_offset.get(int(y_offset)):
                self.font_dict[class_name] = font_dict_by_offset[int(y_offset)][int(x_offset)]
        # special treat
        self.font_dict['zltswc']='工'
        self.font_dict['zuc30h']='堆'
        self.font_dict['xl06i'] = '丁'
        return self.font_dict

    def _data_pipeline(self, data):
        """
            处理数据
        """
        if self.r.llen(self.shop_id) > 0 and data is not None:
            self.r.rpushx(self.shop_id, json.dumps(data))
        else:
            if isinstance(data, str):
                self.r.rpush(self.shop_id, data)
            self.r.rpush(self.shop_id, json.dumps(data))
        print('最终数据:',data)

    def _parse_shop_name(self, doc):
        shop_name = doc.xpath('.//h1[@class="shop-name"]/text()')[0].strip('\n\r \t')
        self.shop_name = shop_name
        data = {"shop_name": shop_name}
        self._data_pipeline(data)

    def _parse_comment_page(self, doc):
        """
            解析评论页并提取数据
        """
        for li in doc.xpath('//*[@class="reviews-items"]/ul/li'):

            name = li.xpath('.//a[@class="name"]/text()')[0].strip('\n\r \t')
            try:
                star = li.xpath('.//span[contains(./@class, "sml-str")]/@class')[0]
                star = re.findall(r'sml-rank-stars sml-str(.*?) star', star)[0]
            except IndexError:
                star = 0
            time = li.xpath('.//span[@class="time"]/text()')[0].strip('\n\r \t')
            pics = []

            if li.xpath('.//*[@class="review-pictures"]/ul/li'):
                for pic in li.xpath('.//*[@class="review-pictures"]/ul/li'):
                    print(pic.xpath('.//a/@href'))
                    pics.append(pic.xpath('.//a/img/@data-big')[0])
            comment = ''.join(li.xpath('.//div[@class="review-words Hide"]/text()')).strip('\n\r \t')
            if not comment:
                comment = ''.join(li.xpath('.//div[@class="review-words"]/text()')).strip('\n\r \t')

            data = {
                'name': name,
                'comment': comment,
                'star': star,
                'pic': pics,
                'time': time,
            }
            self._data_pipeline(data)

    def _get_conment_page(self):  # 获得评论内容
        """
            请求评论页，并将<span></span>样式替换成文字
        """
        while self._cur_request_url:
            self._delay_func()
            print('[{now_time}] {msg}'.format(now_time=datetime.datetime.now(), msg=self._cur_request_url))
            res = requests.get(self._cur_request_url, headers=self._default_headers, cookies=self._cookies)
            html = res.text
            class_set = set()
            for svgmtsi in re.findall(r'<svgmtsi class="([a-zA-Z0-9]{5,6})"></svgmtsi>', html):
                class_set.add(svgmtsi)
            for class_name in class_set:
                html = re.sub('<svgmtsi class="%s"></svgmtsi>' % class_name, self._font_dict[class_name], html)
            doc = etree.HTML(html)
            if not self.shop_name or not json.loads(self.r.lindex(self.shop_id, 0)).get("shop_name", None):
                self._parse_shop_name(doc)
            self._parse_comment_page(doc)
            try:
                self._default_headers['Referer'] = self._cur_request_url
                next_page_url = 'http://www.dianping.com' + doc.xpath('.//a[@class="NextPage"]/@href')[0]
                assert next_page_url, IndexError
                self.r.hset(Break_Point, self.shop_id, next_page_url)
            except IndexError:
                next_page_url = None
                print("需要验证了")
            self._cur_request_url = next_page_url

    def run(self):
        self._css_link = self._get_css_link(self._cur_request_url)
        print('css 的连接', self._css_link)
        self._font_dict = self._get_font_dict(self._css_link)
        # self._get_conment_page()


if __name__ == "__main__":
    # COOKIES = '_lxsdk_cuid=175a88be2f2c8-07dbb17c3f0c2f-163e6152-fa000-175a88be2f2c8; _lxsdk=175a88be2f2c8-07dbb17c3f0c2f-163e6152-fa000-175a88be2f2c8; _hc.v=eec61957-8eac-8682-502e-3a53a9f38674.1604850541; s_ViewType=10; Hm_lvt_602b80cf8079ae6591966cc70a3940e7=1604850542,1604850620; cy=2; cye=beijing; ll=7fd06e815b796be3df069dec7836c3df; ua=13811275737; ctu=1d3cf8bd0ab16c6c5c01abe1c3d223d84cde85741f735cebe59c31bbe3281ea7; fspop=test; _lxsdk_s=175faa41390-8c9-72c-1f4%7C%7C48; Hm_lpvt_602b80cf8079ae6591966cc70a3940e7=1606227914'
    COOKIES = "_lxsdk_cuid=175a88be2f2c8-07dbb17c3f0c2f-163e6152-fa000-175a88be2f2c8; _lxsdk=175a88be2f2c8-07dbb17c3f0c2f-163e6152-fa000-175a88be2f2c8; _hc.v=eec61957-8eac-8682-502e-3a53a9f38674.1604850541; s_ViewType=10; Hm_lvt_602b80cf8079ae6591966cc70a3940e7=1604850542,1604850620; cy=2; cye=beijing; ll=7fd06e815b796be3df069dec7836c3df; ua=13811275737; ctu=1d3cf8bd0ab16c6c5c01abe1c3d223d84cde85741f735cebe59c31bbe3281ea7; fspop=test; lgtoken=09f2cc820-43af-474e-8f78-1ea517a3086d; dper=a277159e0fe49787438daa0f4ba377884a64dd1e7b10993f80c29d66ca65f06a39b1309f9b2d49757895a6395b0084ab230ade76b804db65b0f1a66d70ca5333a277f5420f77109e8e11b5898a332b56e01734cad1ca3f7450966e98e55a81f6; dplet=0cc0c500c9ecd54d482baa45bac2c14e; Hm_lpvt_602b80cf8079ae6591966cc70a3940e7=1607246238; _lxsdk_s=1763755191f-521-2f0-c0%7C%7C122"

    dp = DianpingComment('l4VJZIvbUxZOp3ah', cookies=COOKIES)
    dp.run()
