from concurrent.futures import ThreadPoolExecutor
import uuid

task_status = {}
executor = ThreadPoolExecutor(max_workers=4)