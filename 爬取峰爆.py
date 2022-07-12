import re
import os
import asyncio
import aiohttp
import aiofiles
import requests
from lxml import etree
from urllib import parse
from Crypto.Cipher import AES


def get_page_source(url):
    resp = requests.get(url)
    return resp.text
def get_iframe_src(url):
    print("获取iframe的src值")
    # 1. 拿到视频页的页面源代码.
    page_source = get_page_source(url)
    # 2. 从视频页的页面源代码中找到对应的iframe, 提取到iframe里面的src
    tree = etree.HTML(page_source)
    src = tree.xpath("//iframe/@src")[0]
    # /js/player/?url=https://video.buycar5.cn/20200824/1EcQQ5Ww/index.m3u8&id=30288&num=1&count=1&vt=1
    src_url = parse.urljoin(url, src)
    print("成功获取iframe的src值", src_url)
    return src_url
def get_first_m3u8_url(src_url):
    print("获取第一层M3U8地址")
    page_source = get_page_source(src_url)
    # 在js里提取数据. 最好用的方案: re
    obj = re.compile(r'url: "(?P<m3u8_url>.*?)",', re.S)
    result = obj.search(page_source)
    m3u8_url = result.group("m3u8_url")
    print("成功获取到第一层M3U8地址")
    return m3u8_url
def download_m3u8_file(first_m3u8_url):
    print("下载第二层M3U8地址")
    # 获取到第二层M3U8文件, 并保存在硬盘中
    first_m3u8 = get_page_source(first_m3u8_url)
    second_m3u8_url = first_m3u8.split()[-1]
    second_m3u8_url = parse.urljoin(first_m3u8_url, second_m3u8_url)

    # 下载第二层M3U8文件
    second_m3u8 = get_page_source(second_m3u8_url)
    with open("second_m3u8.txt", mode='w', encoding='utf-8') as f:
        f.write(second_m3u8)
    print("下载第二层M3U8成功....数据以保存在second_m3u8.txt 文件中....")
async def download_one(url, sem):  # url: ts文件的下载路径
    async with sem:
        # 自省
        #如果一次下载不成功，我们重新下载，但是下载总数不超过10次
        for i in range(10):
            try:
                file_name = url.split("/")[-1]
                async with aiohttp.ClientSession() as session:  # requests, requests.session()
                    async with session.get(url) as resp:
                        content = await resp.content.read()
                        #下载的ts文件写进电影_源_加密后文件夹中
                        async with aiofiles.open(f"./video_1/{file_name}", mode="wb") as f:
                            await f.write(content)
                print(url, "下载成功")
                break
            except:
                            print("下载失败, 出现错误", url)
                            # time.sleep() # 可以适当的进行睡眠
                            # 异步爬虫没必要
                            await asyncio.sleep((i+1) * 5)
#先读取second_m3u8.txt，找到ts文件的url
async def download_all_ts():
    tasks = []
    #控制协程数量
    sem = asyncio.Semaphore(100)
    #先读取second_m3u8.txt
    with open("second_m3u8.txt", mode="r", encoding='utf-8') as f:
        for line in f:
            #遍历出一个txt里面的每行
            if line.startswith("#"):
                continue    #如果这行是以#开头，我们忽略这一行

            line = line.strip()  # 移除字符串头尾空格或换行符，必须处理
            # task = asyncio.create_task(download_one(line))
            task = asyncio.ensure_future(download_one(line, sem))
            tasks.append(task)
    await asyncio.wait(tasks)
def get_key():
    obj = re.compile(r'URI="(?P<key_url>.*?)"')
    key_url = ""
    with open("second_m3u8.txt", mode="r", encoding='utf-8') as f:
        result = obj.search(f.read())
        key_url = result.group("key_url")
    # 请求到key的url, 获取到真正的秘钥
    key_str = get_page_source(key_url)
    print("已经获取真正的秘钥")
    return key_str.encode('utf-8')
async def des_one(file, key):
    print("即将开始解密", file)
    # 加密解密对象创建
    aes = AES.new(key=key, IV=b"0000000000000000", mode=AES.MODE_CBC)
    async with aiofiles.open(f"./video_1/{file}", mode="rb") as f1, \
            aiofiles.open(f"./video_2/{file}", mode="wb") as f2:
        # 从加密后的文件中读取出来. 进行解密. 保存在未加密文件中
        content = await f1.read()
        bs = aes.decrypt(content)
        await f2.write(bs)
    print("文件已经解密", file)
async def des_all_ts_file(key):
    tasks = []
    with open("second_m3u8.txt", mode="r", encoding='utf-8') as f:
        for line in f:
            if line.startswith("#"):
                continue
            line = line.strip()
            file_name = line.split("/")[-1]
            # 准备异步操作
            task = asyncio.ensure_future(des_one(file_name, key))
            # task = asyncio.ensure_future(download_one(line))
            tasks.append(task)

    await asyncio.wait(tasks)
def merge_ts():
    file_list = []
    with open("second_m3u8.txt", mode='r', encoding='utf-8') as f:
        for line in f:
            if line.startswith("#"):
                continue
            line = line.strip()
            file_name = line.split("/")[-1]  # 获取到文件的名称
            file_list.append(file_name)
    os.chdir("./video_2")
    temp = []
    n = 1  # 合并的次数
    for i in range(len(file_list)):
        file_name = file_list[i]
        temp.append(file_name)  # [1.ts, 2.ts, 3.ts]
        # if i % 50 ==0 and i != 0:
        if len(temp) == 50:
            # 合并一批ts文件
            cmd = f"copy /b {'+'.join(temp)}  {n}.ts"
            r = os.popen(cmd)
            print(r.read())
            # 归零
            temp = []
            n += 1

    # 如果最后还剩下xxx个, 把剩余的再次合并一次
    # 合并一批ts文件
    cmd = f"copy /b  {'+'.join(temp)}  {n}.ts"
    r = os.popen(cmd)
    print(r.read())
    n += 1  # 这里为什么n+=1

    # 第二次大合并
    second_temp = []
    for i in range(1, n):
        second_temp.append(f"{i}.ts")

    cmd = f"copy /b {'+'.join(second_temp)}  峰爆.mp4"
    r = os.popen(cmd)
    print(r.read())

    os.chdir("../")


def main():
    url = "http://www.wbdy.tv/play/44564_1_1.html"
    src_url = get_iframe_src(url)
    # 3.访问src_url. 提取到第一层m3u8文件地址
    first_m3u8_url = get_first_m3u8_url(src_url)
    download_m3u8_file(first_m3u8_url)
    asyncio.run(download_all_ts())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(download_all_ts())
    # # 进行解密
    key = get_key()
    asyncio.run(des_all_ts_file(key))

    # 合并ts文件
    merge_ts()


if __name__ == '__main__':
    main()