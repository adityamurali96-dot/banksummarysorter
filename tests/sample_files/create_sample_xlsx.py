#!/usr/bin/env python3
"""
Generate sample XLSX test files for bank statement processor.
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import pandas as pd
except ImportError:
    print("pandas not installed. Run: pip install pandas openpyxl")
    sys.exit(1)

def create_sample_hdfc():
    """Create a sample HDFC-style bank statement."""
    data = {
        'Date': [
            '15/01/2025', '16/01/2025', '17/01/2025', '17/01/2025',
            '18/01/2025', '19/01/2025', '20/01/2025', '21/01/2025',
            '22/01/2025', '23/01/2025', '24/01/2025', '25/01/2025'
        ],
        'Narration': [
            'SALARY CREDIT FOR JAN 2025',
            'ATM WDL/HDFC/MUMBAI',
            'SWIGGY ORDER 45678',
            'UPI/AMAZON PAY INDIA',
            'NEFT CR FROM XYZ CORP',
            'TATA POWER ELECTRICITY',
            'IRCTC BOOKING REF 9876543',
            'HDFC MF SIP PURCHASE',
            'INDIAN OIL FUEL',
            'HOTSTAR SUBSCRIPTION',
            'HOUSE RENT PAYMENT',
            'GROWW INVESTMENTS'
        ],
        'Withdrawal Amt': [
            '', '15000.00', '380.00', '1800.00',
            '', '2100.00', '750.00', '10000.00',
            '2500.00', '299.00', '30000.00', '5000.00'
        ],
        'Deposit Amt': [
            '85000.00', '', '', '',
            '10000.00', '', '', '',
            '', '', '', ''
        ],
        'Closing Balance': [
            '185000.00', '170000.00', '169620.00', '167820.00',
            '177820.00', '175720.00', '174970.00', '164970.00',
            '162470.00', '162171.00', '132171.00', '127171.00'
        ]
    }

    # Create DataFrame with some header rows (like real bank statements)
    output_path = os.path.join(os.path.dirname(__file__), 'sample_hdfc.xlsx')

    # Create workbook with header info
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Write some bank info at the top
        info_df = pd.DataFrame({
            'A': ['HDFC Bank Statement', 'Account No: XXXX1234', 'Period: Jan 2025', '', '']
        })
        info_df.to_excel(writer, sheet_name='Statement', index=False, header=False)

        # Write the actual data starting at row 5
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='Statement', index=False, startrow=5)

    print(f"Created: {output_path}")


def create_sample_icici():
    """Create a sample ICICI-style bank statement."""
    data = {
        'Transaction Date': [
            '2025-01-15', '2025-01-16', '2025-01-17', '2025-01-18',
            '2025-01-19', '2025-01-20', '2025-01-21', '2025-01-22'
        ],
        'Description': [
            'PAYROLL CREDIT - TECH CORP',
            'ATM-CASH WITHDRAWAL',
            'ZOMATO FOOD DELIVERY',
            'FLIPKART MARKETPLACE',
            'BESCOM BILL PAYMENT',
            'OLA CABS TRIP',
            'MUTUAL FUND SIP - ICICI PRU',
            'BPCL FUEL STATION'
        ],
        'Debit': [
            '', '20000', '550', '3500',
            '1800', '420', '8000', '3000'
        ],
        'Credit': [
            '95000', '', '', '',
            '', '', '', ''
        ],
        'Balance': [
            '195000', '175000', '174450', '170950',
            '169150', '168730', '160730', '157730'
        ]
    }

    output_path = os.path.join(os.path.dirname(__file__), 'sample_icici.xlsx')

    df = pd.DataFrame(data)
    df.to_excel(output_path, index=False)

    print(f"Created: {output_path}")


def create_sample_messy_csv():
    """Create a messy CSV with garbage rows and multi-line transactions."""
    content = """Statement of Account
Account Number: XXXX5678
Date,Particulars,Debit,Credit,Balance
Page 1
15/01/2025,SALARY CREDIT FOR JAN,,90000.00,190000.00
16/01/2025,ATM WDL/SBI ATM,20000.00,,170000.00
Date,Particulars,Debit,Credit,Balance
17/01/2025,SWIGGY INSTAMART,350.00,,169650.00
,GROCERY DELIVERY,,,
18/01/2025,UPI/PAYTM/MERCHANT,1500.00,,168150.00
Page 2
19/01/2025,NEFT CR FROM ABC CORP,,8000.00,176150.00
,PROJECT PAYMENT,,,
,REF NO 123456,,,
20/01/2025,NETFLIX MONTHLY,649.00,,175501.00
Date,Particulars,Debit,Credit,Balance
21/01/2025,SBI MF SIP,5000.00,,170501.00
Opening Balance,,,190000.00
Closing Balance,,,170501.00
Total,,,27149.00,98000.00
"""

    output_path = os.path.join(os.path.dirname(__file__), 'sample_messy.csv')
    with open(output_path, 'w') as f:
        f.write(content)

    print(f"Created: {output_path}")


if __name__ == '__main__':
    print("Creating sample test files...")
    create_sample_hdfc()
    create_sample_icici()
    create_sample_messy_csv()
    print("Done!")
