import json
from pathlib import Path

from django.core.management.base import BaseCommand

from tracker.api import api


class Command(BaseCommand):
    help = 'Export the live Ninja OpenAPI contract'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='../../packages/contracts/openapi.json')

    def handle(self, *args, **options):
        path = Path(options['output'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(api.get_openapi_schema(), ensure_ascii=False, indent=2) + '\n')
        self.stdout.write(str(path.resolve()))
