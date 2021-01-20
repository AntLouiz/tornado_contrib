import jwt
import re
import datetime
import settings
from tornado.web import Finish
from contrib.auth.jwt.models import RevokedToken
from contrib.auth.jwt.decorators import _extract_token, decode_access_token, DATABASE_NAME
from contrib.auth.models import User
from contrib.auth.authenticators import BaseAuthentication


class JwtAuthentication(BaseAuthentication):
    unauthorized_message = {"error": 'Access Token is missing or invalid'}

    async def authenticate(self, request, handler, *args, **kwargs):
        is_authenticated = await self.verify_handler_jwt(handler, args, kwargs)
        return is_authenticated


    async def verify_handler_jwt(self, handler, *args, **kwargs):
        handler_object = handler

        try:
            token = _extract_token(handler_object)
            token_data = await self.validate_token(
                handler_object,
                token
            )

            handler_object.jwt_user = token_data['jwt_user']
            handler_object.jti = token_data['jti']

        except (jwt.ExpiredSignatureError, jwt.exceptions.DecodeError) as e:
            expired_msg = str(e)
            return self.is_unauthorized(msg=expired_msg)

        return args, kwargs

    async def validate_token(self, handler_object, token, check_refresh=True):
        valid_token = decode_access_token(token)

        if not valid_token:
            return self.is_unauthorized(msg='Invalid access token')

        jwt_username = valid_token.get('username')
        db_client = handler_object.settings['db_client']
        database = db_client[DATABASE_NAME]
        revoked_tokens = RevokedToken(database)
        user = User(database)

        query_filter = {'username': jwt_username, 'is_active': True}
        queryset = await user.manager.find(query_filter, many=False, remove_fields=['_id'])
        if not queryset.total:
            msg = 'User not found'
            self.unauthorized_message = {'error': msg}
            return False

        print(queryset.asdict())
        user = User(raw_data=queryset.asdict())

        queryset = await revoked_tokens.manager.find({'jti': token})
        if queryset.total != 0:
            return self.is_unauthorized(msg='Current token was revoked')

        if check_refresh:
            is_refresh_token = valid_token.get('refresh_token', False)

            if is_refresh_token:
                return self.is_unauthorized(msg='Invalid access token')

        jwt_user = user.to_primitive()
        token_data = {
            'jwt_user': jwt_user,
            'jti': token
        }

        return token_data

    def is_unauthorized(self, msg):
        self.unauthorized_message['error'] = msg
        return False
