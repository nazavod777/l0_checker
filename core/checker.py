import asyncio
from random import choice

import aiohttp
from eth_abi import encode
from eth_account import Account
from eth_account.account import LocalAccount
from loguru import logger
from web3.auto import w3

from data import config
from utils import append_file
from utils import get_proxy
from utils import loader


class Checker:
    def __init__(self,
                 client: aiohttp.ClientSession,
                 account: LocalAccount):
        self.client: aiohttp.ClientSession = client
        self.account: LocalAccount = account

    async def check_eligible(self) -> bool:
        while True:
            response_text: None = None

            try:
                r: aiohttp.ClientResponse = await self.client.get(
                    url=f'https://www.layerzero.foundation/api/allocation/{self.account.address}',
                    proxy=get_proxy()
                )
                response_text: str = await r.text()
                response_json: dict = await r.json(content_type=None)

                if response_json.get('isEligible', None) is not None:
                    return response_json['isEligible']

                elif response_json.get('error', '') == 'Record not found':
                    return False

                else:
                    logger.error(
                        f'{self.account.address} | Unexpected Response When Checking Eligible: {response_text}')

            except Exception as error:
                if response_text:
                    logger.error(f'{self.account.address} | Unexpected Error When Checking Eligible: {error}, '
                                 f'response: {response_text}')

                else:
                    logger.error(f'{self.account.address} | Unexpected Error When Checking Eligible: {error}')

    async def check_claimed_amount(self) -> bool:
        while True:
            response_text: None = None

            try:
                r: aiohttp.ClientResponse = await self.client.post(
                    url=choice(config.RPC_URLS_LIST),
                    json={
                        'id': 1,
                        'jsonrpc': '2.0',
                        'method': 'eth_call',
                        'params': [
                            {
                                'to': '0xd6b6a6701303b5ea36fa0edf7389b562d8f894db',
                                'data': '0x7a692982' + encode(
                                    types=['address'],
                                    args=[w3.to_checksum_address(value=self.account.address)]
                                ).hex()
                            }
                        ]
                    }
                )

                response_text: str = await r.text()
                response_json: dict = await r.json(content_type=None)
                claimed_amount: int = int(response_json['result'], 16)

                return claimed_amount > 0

            except Exception as error:
                if response_text:
                    logger.error(f'{self.account.address} | Unexpected Error When Checking Is Claimed: {error}, '
                                 f'response: {response_text}')

    async def check_account(self) -> None:
        is_eligible: bool = await self.check_eligible()

        if not is_eligible:
            logger.error(f'{self.account.address} | Not Eligible')
            return

        is_claimed: bool = await self.check_claimed_amount()

        if is_claimed:
            logger.error(f'{self.account.address} | Claimed')
            return

        logger.success(f'{self.account.address} | Claimable')

        async with asyncio.Lock():
            await append_file(
                file_path='result/unclaimed.txt',
                file_content=f'{self.account.key.hex()}\n'
            )


async def check_account(
        client: aiohttp.ClientSession,
        private_key: str
) -> None:
    async with loader.semaphore:
        try:
            account: LocalAccount = Account.from_key(private_key)

        except ValueError:
            logger.error(f'{private_key} | Invalid Private Key')
            return

        checker: Checker = Checker(
            client=client,
            account=account
        )
        await checker.check_account()
