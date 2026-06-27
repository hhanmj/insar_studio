# -*- coding: utf-8 -*-
"""
Created on Sat Oct 14 21:29:03 2023

针对新版欧空局数据下载网站
使用OData API与Wget批量下载Sentinel-2 MSI数据

使用方法介绍文章
https://mp.weixin.qq.com/s/8vWCMYy_pkwauVkwZd3rYQ

过程参考 CSDN——hyzhao_RS
https://blog.csdn.net/mrzhy1/article/details/132921422

OData API官方文档
https://documentation.dataspace.copernicus.eu/APIs/OData.html#query-by-geographic-criteria

Access token官方文档
https://documentation.dataspace.copernicus.eu/APIs/Token.html

@author: 微信公众号——海研人
"""

import os
import sys
import pandas as pd
import requests
import json
import subprocess
import datetime
#%% 基础设置
############################################################################
# 1 起始日期
startDate='2023-09-25'
endDate  ='2023-10-14'

# 2 所需卫星数据
satellite='SENTINEL-2'

# 3 检索时文件名需包括的字符串  对于哨兵2 可以用来筛选区块或者产品等级
contains_str='RVQ'

# 4 检索区域 可在该网站绘制geojson文件 https://geojson.io/#map=5.12/34.13/122.8
roi_geojson='Yangtze.geojson'

# 5 数据保存路径
output_dir='Z:/CSY/Data/'

# 6 新版哥白尼数据中心账号密码 即这个网站的账号密码 https://dataspace.copernicus.eu/
email="更换为你的账号"
password="更换为你的密码"
############################################################################

with open(roi_geojson, 'r') as f:
    data = f.read()
geojson_data = json.loads(data)
coordinates=geojson_data['features'][0]['geometry']['coordinates'][0]
coordinates_str=''
for i in range(len(coordinates)):
    coordinates_str=coordinates_str+str(coordinates[i][0])+' '+str(coordinates[i][1])+', '
coordinates_str=coordinates_str[:-2]

#%% 链接示例 完整检索链接由下面各个部分组合而来
## 基础前缀
# https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=

## 检索条件 不同条件之间需要加 and
# 名字包含条件
# contains(Name,'需要包含的字符串')
# 指定卫星 甚至能下landsat 见文档
# Collection/Name eq 'SENTINEL-3'
# 指定区域 最后一个点坐标需与第一个点坐标相同 可由geojson文件决定
# OData.CSC.Intersects(area=geography'SRID=4326;POLYGON((122 32, 122 30.5, 124 30.5, 124 32, 122 32))')
# 指定起始时间
# ContentDate/Start gt 2022-05-20T00:00:00.000Z and ContentDate/Start lt 2022-05-21T00:00:00.000Z

## 检索属性 添加属性时要紧接检索条件 不能有空格
# 检索上限 不设置该项的话默认为20个 设置的话最大为1000
# &$top=N
# 扩展检索结果的属性 添加后 检索结果中会多一项Assets 里面包含快视图id
# &$expand=Assets

## 将上面各项按需结合便可得到用于检索数据的url 如下
# https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=contains(Name,'EFR') and Collection/Name eq 'SENTINEL-3' and OData.CSC.Intersects(area=geography'SRID=4326;POLYGON((122 32, 122 30.5, 124 30.5, 124 32, 122 32))') and ContentDate/Start gt 2022-05-20T00:00:00.000Z and ContentDate/Start lt 2022-05-21T00:00:00.000Z &$expand=Assets
# 即 检索名称中包含'EFR'、覆盖指定区域、指定时间内 的 哨兵3影像 并包括拓展属性

#%% 生成检索链接
#基础前缀
base_prefix="https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter="
#检索条件 记得检索条件之间要加 and
str_in_name="contains(Name,'"+contains_str+"')"
collection="Collection/Name eq '"+satellite+"'"
roi="OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(("+coordinates_str+"))') "
time_range="ContentDate/Start gt "+startDate+"T00:00:00.000Z and ContentDate/Start lt "+endDate+"T00:00:00.000Z"
#检索属性
search_lim="&$top=1000"
expand_assets="&$expand=Assets"

#最终的检索链接 记得检索条件之间要加 and
request_url=base_prefix+str_in_name+" and "+collection+" and "+roi+" and "+time_range+search_lim+expand_assets

#%% 进行检索
JSON = requests.get(request_url).json()
df = pd.DataFrame.from_dict(JSON['value'])
if len(df)==0:
    print('未查询到数据')
    sys.exit()

columns_to_print = ['Id', 'Name','S3Path','GeoFootprint']
df[columns_to_print].head(3)

#原始数据id列表
data_id_list=df.Id
data_name_list=df.Name

# #快视图下载链接 快视图是可以直接下载的不需要Access token
# quickview_url=[file[0]['DownloadLink'] for file in df.Assets]
# quickview_url_txt = open("quickview_url.txt", "w")
# for item in quickview_url:
#     quickview_url_txt.write(item + "\n")
# quickview_url_txt.close()

#%% 获取Access token
def get_access_token(username: str, password: str) -> str:
    data = {
        "client_id": "cdse-public",
        "username": username,
        "password": password,
        "grant_type": "password",
        }
    try:
        r = requests.post("https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
        data=data,
        )
        r.raise_for_status()
    except Exception as e:
        raise Exception(
            f"Access token creation failed. Reponse from the server was: {r.json()}"
            )
    return r.json()["access_token"]

# Access token有效期仅为十分钟 可以在每次下载数据前都申请一个新的Access token
# access_token = get_access_token(email, password)

#%% 生成供wget进行下载的请求字符串
# 示例
# wget  --header "Authorization: Bearer $ACCESS_TOKEN" 'http://catalogue.dataspace.copernicus.eu/odata/v1/Products(db0c8ef3-8ec0-5185-a537-812dad3c58f8)/$value' -O example_odata.zip
# 注意！！！！！ 此处经我多次尝试 不知为何下载链接的外围要用双引号才能用wget运行 而不是单引号  ACCESS_TOKEN前面不需要加$

wget_str=[]
part1='''wget  --header "Authorization: Bearer '''
part2='''" "http://catalogue.dataspace.copernicus.eu/odata/v1/Products('''
part3=''')/$value" -O '''
for i in range(len(data_id_list)):
    access_token = get_access_token(email, password)
    command=part1+access_token+part2+data_id_list[i]+part3+output_dir+data_name_list[i]+'.zip'
    wget_str.append(command)
    try:
        print('[',datetime.datetime.strftime(datetime.datetime.now(),'%H:%M:%S'),'] '+'开始下载: '+data_name_list[i])
        subprocess.run(command, shell=True, check=True)
        print('[',datetime.datetime.strftime(datetime.datetime.now(),'%H:%M:%S'),'] '+'下载成功: '+data_name_list[i])
    except:
        print('[',datetime.datetime.strftime(datetime.datetime.now(),'%H:%M:%S'),'] '+'下载失败: '+data_name_list[i])
