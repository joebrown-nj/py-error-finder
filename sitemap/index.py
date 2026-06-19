import argparse
import threading
import time
import sys
from pathlib import Path
from collections import deque
from urllib.request import urlopen
from urllib.request import Request
from urllib.error import URLError
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.parse import urlparse
import email.utils as eut

from pprint import pprint
# from var_dump import var_dump
from lxml import etree
from lxml.html.soupparser import fromstring

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crawler_common import DEFAULT_HEADERS, format_duration, normalize_url

# sudo apt-get install python-beautifulsoup
# sudo apt-get install python-pip
# sudo apt-get install python3-pip
# pip3 install setuptools
# pip3 install var_dump

queue = deque()
queued_urls = set()
checked = []
checked_urls = set()
threads = []
types = 'text/html'
state_lock = threading.Lock()

link_threads = []

MaxThreads = 4

parser = argparse.ArgumentParser()
parser.add_argument("url", help="Starting URL")
parser.add_argument("--max-pages", type=int, default=1500)

run_start_time = None

InitialURL = None

InitialURLInfo = None
InitialURLLen = None
InitialURLNetloc = None
InitialURLScheme = None
InitialURLBase = None

netloc_prefix_str = 'www.'
netloc_prefix_len = len(netloc_prefix_str)

run_ini = None
run_end = None
run_dif = None

filename = Path(__file__).resolve().parent / 'sitemap.xml'

request_headers = dict(DEFAULT_HEADERS)
request_headers.update({
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive"
})


def NormalizeURL(url):
    return normalize_url(url)

class RunCrawler(threading.Thread):
    def __init__(self, url):
        threading.Thread.__init__(self)

        self.run_ini = time.time()
        self.run_end = None
        self.run_dif = None
        self.run_start_time = time.time()

        print("")
        print(InitialURL)
        print("")

        if InitialURL == 'HTTPS://SOME_URL.TEST/':
            print ('')
            print ('Change "InitialURL" variable and try again!')
            print ('')
            sys.exit()

        ProcessURL(url)

        self.start()

    def run(self):
        run = True

        while run:
            threads[:] = [thread for thread in threads if thread.is_alive()]
            link_threads[:] = [thread for thread in link_threads if thread.is_alive()]

            while len(threads) < MaxThreads:
                with state_lock:
                    if not queue:
                        break
                    obj = queue.popleft()
                    queued_urls.discard(obj['url'])

                thread = Crawl(obj)
                threads.append(thread)

            if self.run_start_time is None:
                self.run_start_time = time.time()

            elapsed = format_duration(time.time() - self.run_start_time)

            if len(queue) == 0 and len(threads) == 0 and len(link_threads) == 0:
                run = False

                self.done()
            else:
                print ('Threads: ', len(threads), ' Queue: ', len(queue), ' Checked: ', len(checked), ' Link Threads: ', len(link_threads) + 1, ' Elapsed: ', elapsed)
                time.sleep(1)


    def done(self):
        print ('Checked: ', len(checked))
        print ('Running XML Generator...')

        # Running sitemap-generating script
        Sitemap(self.run_start_time)

        self.run_end = time.time()
        self.run_dif = self.run_end - self.run_ini

        print('Crawler Duration: ', format_duration(self.run_dif))


class Sitemap:
    urlset = None
    encoding = 'UTF-8'
    xmlns = 'http://www.sitemaps.org/schemas/sitemap/0.9'

    page_count = 0

    def __init__(self, run_start_time):
        self.run_start_time = run_start_time
        self.root()
        self.children()
        self.xml()

    def done(self):
        print ('Done')

    def root(self):
        self.urlset = etree.Element('urlset')
        self.urlset.attrib['xmlns'] = self.xmlns

    def children(self):
        self.page_count = 0
        for index, obj in enumerate(checked):
            url = etree.Element('url')
            loc = etree.Element('loc')
            lastmod = etree.Element('lastmod')
            changefreq = etree.Element('changefreq')
            priority = etree.Element('priority')

            loc.text = obj['url']
            lastmod_info =  None
            lastmod_header = None
            lastmod.text = None

            if hasattr(obj['obj'], 'info'):
                lastmod_info = obj['obj'].info()
                lastmod_header = lastmod_info["Last-Modified"]

            # check if 'Last-Modified' header exists
            if lastmod_header != None:
                lastmod.text = FormatDate(lastmod_header)

            if loc.text != None:
                url.append(loc)

            if lastmod.text != None:
                url.append(lastmod)

            if changefreq.text != None:
                url.append(changefreq)

            if priority.text != None:
                url.append(priority)

            self.urlset.append(url)
            self.page_count += 1

    def xml(self):
        with open(filename, 'w', encoding='utf-8') as f:
            print(etree.tostring(self.urlset, pretty_print=True, encoding="unicode", method="xml"), file=f)

        print ('Sitemap saved in: ', filename)
        print(f"Total Run Time: {format_duration(time.time() - self.run_start_time)}")
        print(f"Total Pages in Sitemap: {self.page_count}")


class Crawl(threading.Thread):
    def __init__(self, obj):
        threading.Thread.__init__(self)

        self.obj = obj

        self.start()


    def run(self):
        temp_status = None
        temp_object = None

        try:
            temp_req = Request(self.obj['url'], headers=request_headers)
            temp_res = urlopen(temp_req)
            temp_code = temp_res.getcode()
            temp_type = temp_res.info()["Content-Type"]

            temp_status = temp_res.getcode()
            temp_object = temp_res

            if temp_code == 200:
                if types in temp_type:
                    temp_content = temp_res.read()

                    #var_dump(temp_content)

                    try:
                        temp_data = fromstring(temp_content)
                        temp_thread = threading.Thread(target=ParseThread, args=(self.obj['url'], temp_data))
                        link_threads.append(temp_thread)
                        temp_thread.start()
                    except (RuntimeError, TypeError, NameError, ValueError):
                        print ('Content could not be parsed, perhaps it is XML? We do not support that yet.')
                        #var_dump(temp_content)
                        pass

        except URLError as e:
            print ('URLError: ', self.obj['url'])
            temp_status = 000
            pass

        except HTTPError as e:
            print ('HTTPError: ', self.obj['url'])
            temp_status = e.code
            pass

        self.obj['obj'] = temp_object
        self.obj['sta'] = temp_status

        ProcessChecked(self.obj)


def dump(obj):
    '''return a printable representation of an object for debugging'''
    newobj=obj

    if '__dict__' in dir(obj):
      newobj=obj.__dict__

      if ' object at ' in str(obj) and not newobj.has_key('__type__'):
          newobj['__type__']=str(obj)

          for attr in newobj:
              newobj[attr]=dump(newobj[attr])

    return newobj


def FormatDate(datetime):
    datearr = eut.parsedate(datetime)
    date = None

    try:
        year = str(datearr[0])
        month = str(datearr[1])
        day = str(datearr[2])

        if int(month) < 10:
            month = '0' + month

        if int(day) < 10:
            day = '0' + day

        date = year + '-' + month + '-' + day
    except IndexError:
        pprint(datearr)

    return date


def ParseThread(url, data):
    temp_links = data.xpath('//a')

    for temp_index, temp_link in enumerate(temp_links):
        temp_attrs = temp_link.attrib

        if 'href' in temp_attrs:
            temp_url = temp_attrs.get('href')
            temp_src = url

            if not temp_url:
                continue

            temp_url_lc = temp_url.strip().lower()
            if (
                temp_url_lc.startswith('mailto:') or
                temp_url_lc.startswith('tel:') or
                temp_url_lc.startswith('sms:') or
                temp_url_lc.startswith('javascript:') or
                temp_url_lc.startswith('#')
            ):
                continue

            path = JoinURL(temp_src, temp_url)

            if path != False:
                ProcessURL(path, temp_src)


def JoinURL(src, url):
    value = False

    url_info = urlparse(url)
    src_info = urlparse(src)

    if url_info.scheme in ('mailto', 'tel'):
        return value

    url_scheme = url_info.scheme
    src_scheme = src_info.scheme

    url_netloc = url_info.netloc
    src_netloc = src_info.netloc

    if src_netloc.startswith(netloc_prefix_str):
        src_netloc = src_netloc[netloc_prefix_len:]

    if url_netloc.startswith(netloc_prefix_str):
        url_netloc = url_netloc[netloc_prefix_len:]

    if url_netloc == '' or url_netloc == InitialURLNetloc:
        url_path = url_info.path
        src_path = src_info.path

        if url_info.query:
            url_path = url_path + '?' + url_info.query

        src_new_path = urljoin(InitialURLBase, src_path)
        url_new_path = urljoin(src_new_path, url_path)

        path = urljoin(src_new_path, url_new_path)

        #print path

        value = NormalizeURL(path)

    return value


def ProcessURL(url, src = None, obj = None):
    if not url:
        return

    url = NormalizeURL(url)

    with state_lock:
        if url in queued_urls or url in checked_urls:
            return

        temp = {
            'url': url,
            'src': src,
            'obj': obj,
            'sta': None
        }

        queue.append(temp)
        queued_urls.add(url)

def ProcessChecked(obj):
    with state_lock:
        if obj['url'] in checked_urls:
            return

        checked.append(obj)
        checked_urls.add(obj['url'])


def main():
    global args
    global run_start_time
    global InitialURL
    global InitialURLInfo
    global InitialURLLen
    global InitialURLNetloc
    global InitialURLScheme
    global InitialURLBase

    queue.clear()
    queued_urls.clear()
    checked.clear()
    checked_urls.clear()
    threads.clear()
    link_threads.clear()

    args = parser.parse_args()

    run_start_time = time.time()

    InitialURL = args.url
    InitialURLInfo = urlparse(InitialURL)
    InitialURLLen = len(InitialURL.split('/'))
    InitialURLNetloc = InitialURLInfo.netloc
    InitialURLScheme = InitialURLInfo.scheme
    InitialURLBase = InitialURLScheme + '://' + InitialURLNetloc

    if InitialURLNetloc.startswith(netloc_prefix_str):
        InitialURLNetloc = InitialURLNetloc[netloc_prefix_len:]

    RunCrawler(InitialURL)


if __name__ == '__main__':
    main()
