CELERY_ROUTES = {
    'logDeltaUnit': {
        'exchange': 'delta_worker',
        'exchange_type': 'direct',
        'routing_key': 'delta_worker'
    },
    'logTimeUnit': {
        'exchange': 'log_worker',
        'exchange_type': 'direct',
        'routing_key': 'log_worker'
    },
    'logVolumeUnit': {
        'exchange': 'log_worker',
        'exchange_type': 'direct',
        'routing_key': 'log_worker'
    },
}