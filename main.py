import time
import requests
import json
from bs4 import BeautifulSoup
import os
import pickle
from appdirs import user_data_dir

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
    queries = list({f'{title} {author}'.replace('&', 'and')  # some characters such as & and # end the search string prematurely
                    for author in authors[:2]})[:20]  # search by title + series and author, max of 20 queries
    media_items = []
    for library_name in cloudlibrary_urlNames:
        api_url = f'https://ebook.yourcloudlibrary.com/uisvc/{library_name}/Search/CatalogSearch'
        for query in queries:
            params = {
                'media': mediatype,
                'src': 'lib',
            }
            json_payload = {
                "SearchString": query,
                "SortBy": "publication_date",  # sort new > old
                "Segment": 1,
                "SegmentSize": 5
            }
            try:
                r = sess.post(api_url, params=params, json=json_payload, timeout=30)
            except (requests.ConnectionError, requests.exceptions.ReadTimeout) as e:
                print(f'error {e}')
                time.sleep(10)
                continue
            time.sleep(1)
            r_json = r.json()
            if r.status_code == 200 and r_json['Items']:
                for media_item in r_json['Items']:
                    for k, v in list(media_item.items()):
                        media_item[k.lower()] = v
                    media_item['url'] = f'https://ebook.yourcloudlibrary.com/library/{library_name}/Featured/ItemDetail/{media_item["id"]}'
                media_items += r_json['Items']
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
        headers['cookie'] = 'mam_id='

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
            book['title'] = BeautifulSoup(book["title"], features="lxml").text
            if book['authors']:
                book['authors'] = [author for k, author in json.loads(book['authors']).items()]
    return req_books


def main():
    req_books = get_mam_requests()

    req_books_reduced = [x for x in req_books if
                         (x['cat_name'].startswith('Ebooks ') or x['cat_name'].startswith('Audiobooks '))
                         and x['filled'] == 0
                         and x['torsatch'] == 0
                         and x['id'] not in blacklist]
    for book in req_books_reduced:
        mediatype = book['cat_name'].split(' ')[0][:5].lower()  # will be ebook or audio
        hits = []
        hits += search_cloudlibrary(book['title'], book['authors'], mediatype)
        if hits:
            print(book['title'])
            print(' ' * 2 + book['url'])
            if len(hits) > 5:
                print(' ' * 2 + f'got {len(hits)} hits')
                print(' ' * 2 + f'showing first 5 results')
                hits = hits[:5]
            for hit in hits:
                print(' ' * 2 + hit["title"])
                print(' ' * 4 + hit['url'])
            print()


if __name__ == '__main__':
    main()
