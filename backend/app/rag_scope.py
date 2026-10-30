"""PDF page1 is independent of the printed book's page number."""
def selected_pages(ranges,page_count):
    if not ranges:return set(range(1,page_count+1))
    return {p for r in ranges for p in range(r['page_start'],min(r['page_end'],page_count)+1)}

def page_selected(ranges,number):
    return not ranges or any(r['page_start']<=number<=r['page_end'] for r in ranges)
