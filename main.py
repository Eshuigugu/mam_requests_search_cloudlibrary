import time
import requests
import json
import os
import pickle
from appdirs import user_data_dir
import html


# this script does create some files under this directory
appname = "search_cloudlibrary"
appauthor = "Eshuigugu"
data_dir = user_data_dir(appname, appauthor)

cloudlibrary_urlNames = ['NSU']

if not os.path.isdir(data_dir):
    os.makedirs(data_dir)
sess_filepath = os.path.join(data_dir, 'session.pkl')

mam_blacklist_filepath = os.path.join(data_dir, 'blacklisted_ids.txt')
if os.path.exists(mam_blacklist_filepath):
    with open(mam_blacklist_filepath, 'r') as f:
        blacklist = set([int(x.strip()) for x in f.readlines()])
else:
    blacklist = set()

if os.path.exists(sess_filepath):
    sess = pickle.load(open(sess_filepath, 'rb'))
    # only take the cookies
    cookies = sess.cookies
    sess = requests.Session()
    sess.cookies = cookies
else:
    sess = requests.Session()


def search_cloudlibrary(title, authors, mediatype):
    # some characters such as & and # end the search string prematurely
    queries = list({f'{title} {author}'.replace('&', 'and')
                    for author in authors[:2]})[:20]  # search by title, max of 20 queries
    media_items = []
    for library_name in cloudlibrary_urlNames:
        api_url = f'https://ebook.yourcloudlibrary.com/library/{library_name}/search'
        for query in queries:
            params = {
                'format': mediatype,
                'available': 'true',
                'language': '',
                'sort': '',
                'segment': '1',
                'orderBy': 'relevence',
                'owned': 'yes',
                'query': query,
                '_data': 'routes/library/$name/search',
            }
            try:
                r = sess.get(api_url, params=params, timeout=30)
            except (requests.ConnectionError, requests.exceptions.ReadTimeout) as e:
                print(f'error {e}')
                time.sleep(10)
                continue
            time.sleep(1)
            r_json = r.json()
            if r.status_code == 200 and 'items' in r_json['results']['search'] and r_json['results']['search']['items']:
                for media_item in r_json['results']['search']['items']:
                    for k, v in list(media_item.items()):
                        media_item[k.lower()] = v
                    media_item['url'] = f'https://ebook.yourcloudlibrary.com/library/{library_name}/Featured/ItemDetail/{media_item["id"]}'
                media_items += r_json['results']['search']['items']
    # ensure each result is unique
    media_items = list({x['url']: x for x in media_items}.values())
    return media_items


def get_mam_requests(limit=5000):
    keepGoing = True
    start_idx = 0
    req_books = []

    # fetch list of requests to search for
    while keepGoing:
        time.sleep(1)
        url = 'https://www.myanonamouse.net/tor/json/loadRequests.php'
        headers = {}
        # fill in mam_id for first run
        # headers['cookie'] = 'mam_id='

        query_params = {
            'tor[text]': '',
            'tor[srchIn][title]': 'true',
            'tor[viewType]': 'unful',
            'tor[startDate]': '',
            'tor[endDate]': '',
            'tor[startNumber]': f'{start_idx}',
            'tor[sortType]': 'dateD'
        }
        headers['Content-type'] = 'application/json; charset=utf-8'

        r = sess.get(url, params=query_params, headers=headers, timeout=60)
        if r.status_code >= 300:
            raise Exception(f'error fetching requests. status code {r.status_code} {r.text}')

        req_books += r.json()['data']
        total_items = r.json()['found']
        start_idx += 100
        keepGoing = min(total_items, limit) > start_idx and not \
            {x['id'] for x in req_books}.intersection(blacklist)

    # saving the session lets you reuse the cookies returned by MAM which means you won't have to manually update the mam_id value as often
    with open(sess_filepath, 'wb') as f:
        pickle.dump(sess, f)

    with open(mam_blacklist_filepath, 'a') as f:
        for book in req_books:
            f.write(str(book['id']) + '\n')
            book['url'] = 'https://www.myanonamouse.net/tor/viewRequest.php/' + \
                          str(book['id'])[:-5] + '.' + str(book['id'])[-5:]
            book['title'] = html.unescape(str(book['title']))
            if book['authors']:
                book['authors'] = [author for k, author in json.loads(book['authors']).items()]
    return req_books


def should_search_for_book(mam_book):
    # category 79 is magazines/newspapers
    return (mam_book['cat_name'].startswith('Ebooks ') or mam_book['cat_name'].startswith('Audiobooks '))\
           and mam_book['filled'] == 0\
           and mam_book['torsatch'] == 0\
           and mam_book['category'] != 79\
           and mam_book['id'] not in blacklist


def search_for_mam_book(book):
    mediatype = book['cat_name'].split(' ')[0][:5].lower()  # will be ebook or audio
    try:
        return search_cloudlibrary(book['title'], book['authors'], mediatype)
    except Exception as e:
        print('error', e)
        return


def pretty_print_hits(mam_book, hits):
    print(mam_book['title'])
    print(' ' * 2 + mam_book['url'])
    if len(hits) > 5:
        print(' ' * 2 + f'got {len(hits)} hits')
        print(' ' * 2 + f'showing first 5 results')
        hits = hits[:5]
    for hit in hits:
        print(' ' * 2 + hit["title"])
        print(' ' * 4 + hit['url'])
    print()


def main():
    req_books = get_mam_requests()
    for book in filter(should_search_for_book, req_books):
        hits = search_for_mam_book(book)
        if hits:
            pretty_print_hits(book, hits)


if __name__ == '__main__':
    main()

