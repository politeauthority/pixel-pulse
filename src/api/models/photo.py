"""
    Cver Api
    Model - Cluster

"""
from cver.api.models.base_entity_meta import BaseEntityMeta


class Photo(BaseEntityMeta):

    model_name = "photo"

    def __init__(self, conn=None, cursor=None):
        """Create the Image instance."""
        super(Photo, self).__init__(conn, cursor)
        self.table_name = "clusters"
        self.field_map = {
            "id": {
                "name": "id",
                "type": "int",
                "primary": True,
                "api_searchable": True,
            },
            "created_ts": {
                "name": "created_ts",
                "type": "datetime",
            },
            "updated_ts": {
                "name": "updated_ts",
                "type": "datetime",
            },
            "bucket": {
                "name": "bucket",
                "type": "str",
                "extra": "NOT NULL",
                "api_writeable": True,
                "api_searchable": True,
            },
            "file_name": {
                "name": "file_name",
                "type": "str",
                "api_writeable": True,
                "api_searchable": True,
            },
            "photo_set": {
                "name": "photo_set",
                "type": "str",
                "api_writeable": True,
                "api_searchable": True,
            },
            "time_lapse_compiled": {
                "name": "time_lapse_compiled",
                "type": "bool",
                "default": False,
                "api_writeable": True,
                "api_searchable": True,
            },
            "file_size": {
                "name": "file_size",
                "type": "int",
                "api_writeable": True,
                "api_searchable": True,
            }
        }

        self.createable = True
        self.setup()


# End File: cver/src/api/models/photo.py
