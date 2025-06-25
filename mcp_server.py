from fastmcp import FastMCP
from pathlib import Path
import pandas as pd

mcp = FastMCP(name="MyServer")

@mcp.tool
def get_bad_wafer_ids(all_query_data: list) -> list[str]:
    """get bad wafer id list from all query data."""
    print(f"Received all_query_data with {all_query_data} records.")
    df = pd.DataFrame(all_query_data)
    df = df[df['goodbad'] == 1]
    # get wafer_id list 
    wafer_id = df['wafer_id'].tolist()
    return wafer_id

@mcp.resource("minio://{case_name}/all_query_data")
def get_all_query_data(case_name:str) -> dict:
    """reads all query data file from the minio."""
    file_path = f"./case/{case_name}/all_query_data.csv"
    print(file_path)
    if Path(file_path).exists():
        return pd.read_csv(file_path).to_dict(orient='records')
    else:
        # return minio_storage.df.csv
        pass

@mcp.prompt
def count_bad_wafer(bad_wafer_id:str) -> str:
    """Creates a prompt for bad wafer."""
    return f"有以下的bad wafer: {bad_wafer_id}, 告訴我編號最高的bad wafer是哪一個？"

if __name__ == "__main__":
    mcp.run()