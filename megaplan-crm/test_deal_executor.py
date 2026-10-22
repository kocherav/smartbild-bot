import unittest
from unittest.mock import patch
import deal_browser


class API:
    def __init__(self): self.assigned=[]; self.posts=[]
    def _call(self,method,path,params=None,json_body=None):
        if path=='/employee/search':
            return {'data':[{'id':'10','contentType':'Employee','name':'Деревянко Сергей'}]}
        if path=='/employee/10':
            return {'data':{'id':'10','contentType':'Employee','name':'Деревянко Сергей'}}
        if method=='POST' and path=='/deal/900':
            self.posts.append(json_body);self.assigned=json_body['Category1000068CustomFieldIspolnitel'];return {'data':{}}
        if method=='GET' and path=='/deal/900':
            return {'data':{'id':'900','name':'Test','contractor':{'name':'Client'},'state':{'id':'1','name':'Монтаж'},'Category1000068CustomFieldIspolnitel':self.assigned}}
        raise AssertionError((method,path,params,json_body))


class DealExecutorTests(unittest.TestCase):
    def test_search_returns_real_ids(self):
        self.assertEqual(deal_browser.search_employees(API(),'Сергей')['employees'],[{'id':'10','name':'Деревянко Сергей'}])
    def test_set_and_readback(self):
        api=API()
        with patch.object(deal_browser,'update_cached_deal'):
            result=deal_browser.set_executor(api,'900','10')
        self.assertTrue(result['ok']);self.assertEqual(result['deal']['executors'],['Деревянко Сергей'])
        self.assertEqual(api.posts[0]['Category1000068CustomFieldIspolnitel'],[{'contentType':'Employee','id':'10'}])
    def test_readback_mismatch_blocks_success(self):
        api=API()
        original=api._call
        def call(method,path,params=None,json_body=None):
            result=original(method,path,params,json_body)
            if method=='GET' and path=='/deal/900':result['data']['Category1000068CustomFieldIspolnitel']=[]
            return result
        api._call=call
        with self.assertRaisesRegex(ValueError,'обратное чтение'):
            deal_browser.set_executor(api,'900','10')


if __name__=='__main__':unittest.main()
