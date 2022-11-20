import asyncio
from html.parser import HTMLParser
import time 
import requests
from bs4 import BeautifulSoup
import aiohttp
from urllib.parse import urljoin 
import os
import json
from io import BytesIO


#declare global dicts
TREE={}
JSON={}


#get all responses async
async def fetch_page(session,url):
    try:
        async with session.get(url) as response:
            return await response.read()
    except aiohttp.client_exceptions.ClientConnectorError as err:
        print("Server not responding: resending request...")
        fetch_page(session,url)

async def fetch_all_pages(session, urls):
    task_list=[]
    for url in urls:    
        print(f"{url} sent")
        task = asyncio.create_task(fetch_page(session,url) )
        task_list.append(task)

        # * packs excess positional arguments into a tuple 
    results = await asyncio.gather(*task_list)
    print(f"results received: {len(results)}")
    return results 
       

async def fetch_all_requests(urls):
    async with aiohttp.ClientSession() as session:
        data = await fetch_all_pages(session,urls)
        return data

#helper to add data to JSON dict
def add_data_JSON(name,a):
    global JSON
    #dic is empty create new dict
    if(len(list(JSON.keys())) == 0):       
        JSON= dict(zip(name,a))
    
    #add data to dict
    else:
        keys = list(JSON.keys())
        keys.extend(name)
        values= list(JSON.values())
        values.extend(a)
        JSON= dict(zip(keys,values))



#dummy for getting first div
def parse_href_li(response,url):

    # #get soup to find all links 
    soup= BeautifulSoup(response,"html.parser")
    elements = soup.select('a')

    #only track the external relative links 
    href = {}
    for e in elements:
        # print(e)
        try:
            if (e['rel']==["external"]):
                href[e.get_text().replace('/','-')] = urljoin(url,e.get('href')) 
        except KeyError:
            # print("rel attr doesnt exist for",e.attrs)
            continue
    return href

#find first div    
def parse_href(parent_response):
    soup = BeautifulSoup(parent_response,"html.parser")
    content = soup.find('body').find('div',attrs={"data-role": "content"})
    return content

#tree1
def parse_uncollapsible_content(content,url):
    # print(url)
    dictionary={}
    unordered_list = content.find_all("ul", attrs={"data-role": "listview"} )
    for ul in unordered_list:
        if ul.find_previous('div')["data-role"] != "collapsible":
            list_item = ul.find_all('a')
            for li in list_item:
                dir = li.text.replace('/','-')
                url = urljoin(url,li.get('href'))
                # print(f"-{dir}")
                # print("\t",url)
                dictionary[dir]=url
                if(url[-3:]=='pdf'):
                    add_data_JSON(dir,url)
    return dictionary
    

#parse tree 2
def parse_li_content(li,url,dir):
    global TREE
    #check if h3 exists     
    #link has child directory
    try :
        #get child directory name
        c_dir=urljoin(dir,li.find("h3").text)
        # print(f"\t>{c_dir}") 

        #get all pdfs in child directory
        a = li.find_all("a", attrs={"rel": "external"})
        name = list(map(lambda x: x.text.replace('/','-'),a))
        a = list(map(lambda x: urljoin(url,x.get('href')),a))
        name_a = list(zip(name,a))
        #list comprehension to rm dups
        # a = [a[i] for i in range(len(a)) if i == a.index(a[i]) ]

        #create dictionary key with child dir
        #add list of pdfs as value pair 
        TREE[c_dir]=name_a

    #there is not h3 so no new directory
    #link navigates directly to pdf
    except AttributeError:
        a = li.find_all("a", attrs={"rel": "external"})
        name = list(map(lambda x: x.text.replace('/','-'),a))
        a = list(map(lambda x: urljoin(url,x.get('href')),a))
        name_a = list(zip(name,a))
        # a = [a[i] for i in range(len(a)) if i == a.index(a[i]) ]

        #check if key exits before overriding 
        #if it does add list to values 
        if(TREE.get(dir) != None):
            TREE[dir].extend(name_a)
        else:
            TREE[dir]=name_a
    
    #save PDF data in JSON
    add_data_JSON(name,a)

    return TREE

#tree2
def parse_collapsible_content(content,url,dir):
    print(url)
    global TREE
    dirs=[]
    urls=[]

    #get collapsible divs
    collapsible = content.find_all("div", attrs={"data-role": "collapsible"} )
    for div in collapsible:
        #get directory name of collapsible div
        # p_dir =  urljoin(dir, div.find("h3").text)
        p_dir=dir + "/" +  div.find("h3").text.replace('/','-')
        print(f"-{p_dir}")

        #create link array for div 
        head_li=div.find_next('li', recursive=False)
        tail_li=head_li.find_next_siblings("li",recursive=False)
        li_list = [head_li]
        li_list.extend(tail_li)
        for li in li_list:
            list_content = parse_li_content(li,url,p_dir)
            li_dir = list(list_content.keys())
            dirs.extend(li_dir)
            li_name_url= list(list_content.values())
            urls.extend(li_name_url)

    TREE = dict(zip(dirs,urls))

    print()
    return TREE

#crawler
def crawler(dir,url,href):
    tree1 = parse_uncollapsible_content(parse_href(href),url)
    tree2 = parse_collapsible_content(parse_href(href),url,dir)

    # there is uncollapsible content that needs to be recursed through 
    if(len(tree1)!=0):
        urls = list(tree1.values())
        dirs = list(tree1.keys())

        #temporary work around to remove all pdfs
        urls = list(filter(lambda x: x[-3:]!='pdf',urls))
        pdfs = list(filter(lambda x: x[-3:]=='pdf',urls))
        tree_hrefs = asyncio.run(fetch_all_requests(urls))
        for dir,url,href in zip(dirs,urls,tree_hrefs):
            crawler(dir,url,href)

    #base case should stop crawling at tree2
    return tree2


#write pdfs to directories 
def fetch_all_pdfs(list_pdfs):
    start = time.time()
    list_pdf_content = asyncio.run(fetch_all_requests(list_pdfs))
    end=time.time()
    print(f"request spent: {round(end-start,2)} s\n")
    return list_pdf_content


def writeFile(dir,name,a):
    print(f"\n{dir}")
    for pdf,pdf_content in zip(name,a):
        pdf_name = pdf
        #try to write to dir as it exists 
        try:
            with open(os.path.join(dir,pdf_name),'wb')as f:
                f.write(pdf_content)
        #catch if dir does not exist create dir and write to it
        except FileNotFoundError:
            os.makedirs(dir)
            with open(os.path.join(dir,pdf_name),'wb')as f:
                f.write(pdf_content)
        print(f"{pdf} saved...")
    print()

def dumpJSON(dict,dir,name):
    #write JSON to .json file in parent dir
    jsonO=json.dumps(dict,indent=4)
    try:
        with open(os.path.join(dir,name),'w') as f:
            f.write(jsonO)
    except FileNotFoundError as err:
        os.makedirs(dir)
        with open(os.path.join(dir,name),'w') as f:
            f.write(jsonO)
    print(f"~~succesfully dumped JSON~~")

#main
if __name__ == '__main__':   
    cwd = os.getcwd()
    start=time.time()

# Create for loop to iterate trhough list of urls
    url1= "http://manuals.gogenielift.com/Parts%20And%20Service%20Manuals/1MainPMIndex.htm"
    url2="http://manuals.gogenielift.com/Parts%20And%20Service%20Manuals/PartsScissorsindex.htm"
    url3="http://manuals.gogenielift.com/Parts%20And%20Service%20Manuals/PartsSBoomsIndex.htm"
    url4="https://manuals.genielift.com/Parts%20And%20Service%20Manuals/PartsZBoomsindex.htm"

    #create seperate directory in project folder to store all directories from crawler
    url=url4
    url_index = os.path.basename(os.path.normpath(url))
    parent_directory = cwd+'/'+ url_index

    #get first url to setup crawler
    response= BeautifulSoup(requests.get(url).text,"html.parser")
    dir_urls =  parse_uncollapsible_content(response,url)
    # dir_urls = parse_uncollapsible_content(BeautifulSoup(response,"html.parser"),url)
    dirs = list(dir_urls.keys())
    urls= list(dir_urls.values())
    hrefs = asyncio.run(fetch_all_requests(urls))
    
    tree={}
    for dir,uri,href in zip(dirs,urls,hrefs):
        print(f"_________________{cwd}/{dir}_________________")
        dir=parent_directory+"/"+dir
        #crawl through all links 
        tree = crawler(dir,uri,href)
    
    #dump to file to check json dict
    dumpJSON(tree,parent_directory,"tree_file.json")

    #write pdf to current directory
    for dir,pdf_set in tree.items():
        #unzip tuple into seperate lists
        name,a=zip(*pdf_set)
        pdfs = fetch_all_pdfs(a)
        writeFile(dir,name,pdfs)

    #write JSON to .json file in parent dir
    dumpJSON(JSON,parent_directory,url_index)
    end=time.time()
    duration = round((end-start)/60,2)
    print(f"Completed: {duration}m")