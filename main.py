#!/usr/bin/env python

import json
import os
import random
import time
from getpass import getpass
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union

from pixivpy3 import AppPixivAPI, PixivAPI  # type: ignore
from pixivpy3.utils import JsonDict, PixivError  # type: ignore

'''client.json
{
  'pixiv_id' : '<change this>',
  'password' : '<change this>'
}
'''


class LoginCred(TypedDict):
    pixiv_id: str
    password: str


class IllustInfo(TypedDict):
    id: int
    title: str
    link: Union[str, List[str]]


class UserInfo(TypedDict):
    id: int
    name: str
    account: str
    illusts: List[IllustInfo]


def rand_sleep(base: float=0.1, rand: float=0.5) -> None:
    time.sleep(base + rand * random.random())


def _auth() -> Tuple[PixivAPI, AppPixivAPI, JsonDict]:
    login_cred: Optional[LoginCred] = (
        json.load(open('client.json', 'r'))
        if os.path.exists('client.json') else None)
    api: PixivAPI = PixivAPI()
    api.hosts = 'https://app-api.pixiv.net'
    aapi: AppPixivAPI = AppPixivAPI()

    if login_cred is not None:
        login_info: JsonDict = api.login(
            login_cred['pixiv_id'], login_cred['password'])

        aapi.login(login_cred['pixiv_id'], login_cred['password'])
    else:
        print('[+]ID is mail address, userid, account name.')
        stdin_login = (input('[+]ID: '), getpass('[+]Password: '))
        login_info = api.login(stdin_login[0], stdin_login[1])
        aapi.login(stdin_login[0], stdin_login[1])

    return (api, aapi, login_info)


def auth() -> Tuple[PixivAPI, AppPixivAPI, JsonDict]:
    cnt = 0
    while cnt < 3:
        try:
            return _auth()
        except PixivError as e:
            j = json.loads(e.body)
            print('{} <{}>'.format(j["errors"]["system"]["message"], j["error"]))
            cnt += 1
    else:
        print('The number of login attempts has been exceeded.')
        exit(1)


def retrieve_bookmarks(
        aapi: AppPixivAPI, login_info: JsonDict) -> List[IllustInfo]:
    def ext_links(illust: JsonDict) -> Union[List[str], str]:
        links: List[str] = [
            page.image_urls.original for page in illust.meta_pages]
        link: str = illust.meta_single_page.get(
            'original_image_url', illust.image_urls.large)

        return (links if links != [] else link)

    urls: List[IllustInfo] = []
    next: Optional[Dict[str, Any]] = None
    target_id = login_info.response.user.id
    while True:
        # pagenation
        res_json: JsonDict = (aapi.user_bookmarks_illust(target_id)
                              if next is None
                              else aapi.user_bookmarks_illust(**next))
        urls.extend([
            {
                'id': illust.id,
                'title': illust.title,
                'link': ext_links(illust)}
            for illust in res_json['illusts']])
        next = aapi.parse_qs(res_json['next_url'])
        if not next:
            break
        rand_sleep()

    return urls


def retrieve_works(aapi: AppPixivAPI, id_: int) -> List[IllustInfo]:
    def ext_links(illust: JsonDict) -> Union[List[str], str]:
        links = [page.image_urls.original for page in illust.meta_pages]
        link = illust.meta_single_page.get(
            'original_image_url', illust.image_urls.large)

        return (links if links != [] else link)

    # pagenation
    urls: List[IllustInfo] = []
    next: Optional[Dict[str, Any]] = None
    target_id = id_
    while True:
        # pagenation
        res_json = (aapi.user_illusts(target_id, type='illust')
                    if next is None else aapi.user_illusts(**next))
        urls.extend([{
            'id': illust.id,
            'title': illust.title,
            'link': ext_links(illust)}
            for illust in res_json['illusts']])
        next = aapi.parse_qs(res_json['next_url'])
        if not next:
            break
        rand_sleep()

    return urls


def retrieve_following(
        aapi: AppPixivAPI, login_info: JsonDict) -> List[UserInfo]:
    users: List[UserInfo] = []
    res_json: JsonDict = aapi.user_following(login_info.response.user.id)
    for user in res_json.user_previews:
        user_info: JsonDict = user.user
        users.append({
            "id": user_info.id,
            "name": user_info.name,
            "account": user_info.account,
            "illusts": retrieve_works(aapi, user_info.id)})

    return users


SAVE_DIR = os.path.join(os.path.expanduser("~"), 'pbd')


def download(
        aapi: AppPixivAPI, data: List[IllustInfo],
        save_dir: str = SAVE_DIR) -> None:
    os.makedirs(save_dir, exist_ok=True)
    data_len = len(data)
    for idx, image_data in enumerate(data):
        title, id_ = image_data['title'].replace('/', '／'), image_data['id']
        link = image_data['link']
        print('\033[K' + '[{}/{}]: {}({})'.format(idx + 1, data_len, title, id_))
        if type(link) is list:
            for _ in link:
                basename_: str = _.split('/')[-1]
                fname = '{}_{}_{}'.format(id_, title, basename_.split('_')[-1])
                print('\033[K' + fname, end="\r")
                aapi.download(_, path=save_dir, fname=fname)
        else:
            basename_ = link.split('/')[-1]
            fname = '{}_{}_{}'.format(id_, title, basename_.split('_')[-1])
            print('\033[K' + fname, end="\r")
            aapi.download(link, path=save_dir, fname=fname)


def get_all_following_works(aapi: AppPixivAPI, login_info: JsonDict) -> None:
    following_data = retrieve_following(aapi, login_info)
    following_len = len(following_data)
    for idx, author_data in enumerate(following_data):
        dirname = '{}_{}_{}'.format(
            author_data['id'], author_data['name'],
            author_data['account']).replace('/', '／')
        print('\033[K' + '[{}/{}]: {}'.format(idx + 1, following_len, dirname))
        download(aapi, author_data['illusts'],
                 os.path.join(SAVE_DIR, 'following', dirname))


def get_all_bookmarked_works(aapi: AppPixivAPI, login_info: JsonDict) -> None:
    bookmarked_data = retrieve_bookmarks(aapi, login_info)
    download(aapi, bookmarked_data, os.path.join(SAVE_DIR, 'bookmarks'))


def main() -> None:
    api, aapi, login_info = auth()

    if input('get_all_following_works? [yn]: ') == 'y':
        get_all_following_works(aapi, login_info)
    if input('get_all_bookmarked_works? [yn]: ') == 'y':
        get_all_bookmarked_works(aapi, login_info)


if __name__ == '__main__':
    try:
        main()
    except KeyError as e:
        print(e, 'Request limit seem to be exceeded. Try again later.')
    except KeyboardInterrupt:
        pass
