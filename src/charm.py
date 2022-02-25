#!/usr/bin/env python3
# This file is part of the Redis k8s Charm for Juju.
# Copyright 2021 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import logging

from redis import Redis
from redis.exceptions import RedisError

from charms.redis_k8s.v0.redis import RedisProvides
from ops.main import main
from ops.charm import CharmBase
from ops.model import ActiveStatus, WaitingStatus
from ops.pebble import Layer

REDIS_PORT = 6379
WAITING_MESSAGE = 'Waiting for Redis...'
PEERS = "redis-k8s"

logger = logging.getLogger(__name__)


class RedisCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        self._container = self.unit.get_container("redis")
        self.redis_provides = RedisProvides(self, port=REDIS_PORT)

        self.framework.observe(self.on.redis_pebble_ready, self._redis_pebble_ready)
        self.framework.observe(self.on.config_changed, self._config_changed)
        self.framework.observe(self.on.upgrade_charm, self._config_changed)
        self.framework.observe(self.on.update_status, self._update_status)

        self.framework.observe(self.on.check_service_action, self.check_service)
    

    def _redis_pebble_ready(self, event) -> None:
        """"""
        self._update_layer()
        
    
    def _config_changed(self, event):
        logger.info("Beginning config_changed")
        self._update_layer()
        self._redis_check()

    def _update_status(self, event):
        logger.info("Beginning update_status")
        self._redis_check()
    
    def _redis_layer(self) -> Layer:
        """Return a the configuration Pebble layer for Redis."""
        layer_config = {
            "summary": "Redis layer",
            "description": "Redis layer",
            "services": {
                "redis": {
                    "override": "replace",
                    "summary": "Redis service",
                    "command": "/usr/local/bin/start-redis.sh redis-server",
                    "startup": "enabled",
                    "environment": {
                        "ALLOW_EMPTY_PASSWORD": "yes"
                    }
                }
            }
        }
        return Layer(layer_config)

    def _update_layer(self) -> None:
        """Update the Pebble layer and restart the container"""
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble in workload container")
            return

        # Get current config
        current_layer = self._container.get_plan()
        # Create the config layer
        new_layer = self._redis_layer()

        # Update the Pebble configuration layer
        if current_layer.services != new_layer.services:
            self._container.add_layer("redis", new_layer, combine=True)
            logger.info("Added updated layer 'redis' to Pebble plan")
            self._container.restart("redis")
            logger.info("Restarted redis service")

        self.unit.status = ActiveStatus()
    
    
    def check_service(self, event):
        logger.info("Beginning check_service")
        results = {}
        if self._redis_check():
            results["result"] = "Service is running"
        else:
            results["result"] = "Service is not running"
        event.set_results(results)

    def _redis_check(self):
        try:
            redis = Redis()
            info = redis.info("server")
            version = info["redis_version"]
            self.unit.status = ActiveStatus()
            self.unit.set_workload_version(version)
            if self.unit.is_leader():
                self.app.status = ActiveStatus()
            return True
        except RedisError:
            self.unit.status = WaitingStatus(WAITING_MESSAGE)
            if self.unit.is_leader():
                self.app.status = WaitingStatus(WAITING_MESSAGE)
            return False


if __name__ == "__main__":  # pragma: nocover
    main(RedisCharm)
