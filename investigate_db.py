from scraper.supabase_client import SupabaseClient
import json

def investigate():
    client = SupabaseClient().client
    test_names = [
        'jurisdictions', 
        'scrape_targets', 
        'documents', 
        'document_versions', 
        'document_chunks', 
        'scrape_jobs'
    ]
    
    print("--- Database Table Investigation ---")
    for name in test_names:
        try:
            res = client.table(name).select('*').limit(1).execute()
            print(f"Table [{name}]: EXISTS. Rows: {len(res.data)}")
            if res.data:
                print(f"Columns in [{name}]: {list(res.data[0].keys())}")
        except Exception as e:
            msg = str(e)
            if "PGRST205" in msg:
                print(f"Table [{name}]: NOT FOUND")
            else:
                print(f"Table [{name}]: ERROR: {msg}")

    print("\n--- Testing Insertion into [scrape_jobs] with CORRECT COLUMNS ---")
    try:
        test_data = {
            "status": "testing",
            "items_scraped": 0,
            "items_failed": 0,
            "logs": "Test insertion with schema alignment"
        }
        res = client.table('scrape_jobs').insert(test_data).execute()
        print(f"Insert SUCCESS! Created record ID: {res.data[0]['id']}")
        # Clean up
        client.table('scrape_jobs').delete().eq('id', res.data[0]['id']).execute()
        print("Test record cleaned up.")
    except Exception as e:
        print(f"Insert FAILED: {e}")

if __name__ == "__main__":
    investigate()
