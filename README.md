# EveryAction Tools

Programs for membership migration and contact management with EveryAction

 * `sync_activists.py` - Syncs an Action Network export with EveryAction database
 * `count_tags.py` - Returns count of csv records wih Action Network tags

To run Python scripts

    python sync_activists.py filename.csv

## Organization

## Getting Started

### Installing Python

Windows, Mac?

### Generate API Key

To generate an API Key first "Request an API Key" from through the [API Integrations](https://www.targetsmartvan.com/APIIntegrations.aspx#/) page. For example,

    Integration: Action Network
    Request will be sent to: Evan

Once approved the API Key will appear on the same page with the button "Generate API Key". Record following information:

    Application Name:                   TSURJ.99.99
    One-Time Action Network API Key:    d9999f51-8564-5341-145g-g615d99999af

The API Key is only visible one-time. It can be used multiple times...

### Install EveryAction Client

Install the EveryAction
[Python Client for EveryAction](https://partiallyderived.github.io/everyaction-client/).

    pip install -r requirements.txt

