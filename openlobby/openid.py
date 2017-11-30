from oic.oic import Client
from oic.oic.message import RegistrationResponse, ClaimsRequest, Claims
from oic.utils.authn.client import CLIENT_AUTHN_METHOD

from .settings import SITE_NAME


def init_client_for_uid(openid_uid):
    client = Client(client_authn_method=CLIENT_AUTHN_METHOD)
    issuer = client.discover(openid_uid)
    client.provider_config(issuer)
    return client


def register_client(client, redirect_uri):
    params = {
        'redirect_uris': [redirect_uri],
        'client_name': SITE_NAME,
    }
    client.register(client.provider_info['registration_endpoint'], **params)
    return client


def get_authorization_url(client, state, nonce, is_new_user=True):
    args = {
        'client_id': client.client_id,
        'response_type': 'code',
        'scope': ['openid'],
        'nonce': nonce,
        'state': state,
        'redirect_uri': client.registration_response['redirect_uris'][0],
    }

    if is_new_user:
        args['claims'] = ClaimsRequest(
            userinfo=Claims(
                email={'essential': True},
                name={'essential': True},
            )
        )

    auth_req = client.construct_AuthorizationRequest(request_args=args)
    url = auth_req.request(client.authorization_endpoint)
    return url


def set_registration_info(client, client_id, client_secret, redirect_uri):
    info = {
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uris': [redirect_uri],
    }
    client_reg = RegistrationResponse(**info)
    client.store_registration_info(client_reg)
    return client


def do_access_token_request(client, code, state):
    args = {
        'code': code,
        'client_id': client.client_id,
        'client_secret': client.client_secret,
        'redirect_uri': client.registration_response['redirect_uris'][0],
    }
    client.do_access_token_request(state=state, request_args=args)