# Helper for serializing MongoDB objects
def serialize_doc(doc):
    if not doc:
        return None
    doc['id'] = str(doc['_id'])
    del doc['_id']
    return doc
