import xml.etree.ElementTree as ET
import pandas as pd  # type: ignore
import tempfile
import os
import argparse
from subprocess import call
from configparser import ConfigParser
from typing import Iterator, Any, List, Dict

default_options = {'ledger_indent': 4,
                   'reverse': 'True',
                   'editor': os.getenv('EDITOR'),
                   'rules': None,
                   'ledger_file': None,
                   'def_asset_acc': None,
                   'xml_main': 'Ntry',
                   'csv_offset': 0,
                   'csv_delimiter': ',',
                   'book_date': None,
                   'val_date': None,
                   'creditor': None,
                   'debitor': None,
                   'currency': None,
                   'amount': None,
                   'subject': [None]
                   }


def get_updated_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update default options. Precedence is as follows:
    - command line arguments
    - section for selected account in ini-file
    - section 'main' in ini-file
    """
    config = ConfigParser()
    config.read(os.path.join(os.path.expanduser('~'), 'soa2ledger.ini'))

    parser = argparse.ArgumentParser(
        description='Import statement of account to ledger')
    parser.add_argument('--import_file', type=str,
                        help='Soa file to import')
    parser.add_argument('--account', type=str,
                        choices=config.sections(), help='Account to use')
    parser.add_argument('--dryrun', action='store_true',
                        help="Don't append entries to file.")
    args, unknown = parser.parse_known_args()

    for k, v in config.items('main'):
        options.update({k: v})

    account = args.account
    for k, v in config.items(account):
        options.update({k: v})

    for k, v in vars(args).items():
        options.update({k: v})

    r_conf = ConfigParser()
    r_conf.read(os.path.join(os.path.expanduser('~'), 'soa2ledger-rules.ini'))
    rules = [{k: v for (k, v) in r_conf.items(r)} for r in r_conf.sections()]
    options.update({'rules': rules})

    return options


def iterable_from_file(options) -> List[Iterator]:
    """
    Uses the specified importfile (either .xml or .csv) to return iterable.
    xml:
    - strips all namespaces
    - returns tree iterator based on tag provided by config file
    csv:
    - uses delimiter and offset provided by config file
      to read file into dataframe
    - returns object to iterate over namedtuples
    """
    import_file: str = options.get('import_file')
    if import_file.lower().endswith('.xml'):
        it = ET.iterparse(import_file)
        for _, el in it:
            prefix, has_namespace, postfix = el.tag.partition('}')
            if has_namespace:
                el.tag = postfix  # strip all namespaces
        root = it.root  # type: ignore
        main_tag = options.get('xml_main')
        return list(root.iter(main_tag))
    elif import_file.lower().endswith('.csv'):
        delimiter = options.get('csv_delimiter')
        skiprows = int(options.get('csv_offset'))
        df = pd.read_csv(import_file,
                         delimiter=delimiter,
                         skiprows=skiprows)
        return list(df.itertuples(index=False))
    else:
        raise argparse.ArgumentTypeError(
            "Type of imported file isn't supported!")


def edit_string_with_editor(options, mystring: str) -> str:
    """
    Accepts string and passes it to chosen editor
    to edit it and return edited version.
    """
    editor = options.get('editor')
    with tempfile.NamedTemporaryFile(suffix=".ledger-cap") as tmp:
        tmp.write(mystring.encode('utf-8'))
        tmp.flush()
        call([editor, tmp.name])  # type: ignore
        tmp.seek(0)
        edited_message = tmp.read().decode('utf-8')
        return edited_message


def append_to_ledger(options, entry: str) -> None:
    """
    Appends provided entry to ledger file as defined in options.
    """
    ledger_file = options.get('ledger_file')
    with open(ledger_file, 'a') as ledger_obj:
        ledger_obj.write(entry)


class Entry():
    """
    Represents one entry i.e. transfer in the import file.
    """

    def __init__(self, EL, options: dict):
        self.options = options
        self.EL = EL
        self.def_asset_acc: str = options.get('def_asset_acc')  # type: ignore
        self.book_date = self.eval_rule('book_date')
        self.val_date = self.eval_rule('val_date')
        self.amount = self.eval_rule('amount')
        self.currency = self.eval_rule('currency').replace(".", ",")
        self.creditor: str = self.eval_rule('creditor')
        self.creditor_acc: str
        self.debitor: str = self.eval_rule('debitor')
        self.debitor_acc: str
        self.subject = self.eval_rule('subject')
        self.title = self.creditor

    def eval_rule(self, rule_for: str) -> str:
        """
        Accepts string for rule and looks it up in options.
        Evaluates rule.
        """
        EL = self.EL  # used in config file
        try:
            rule: str = self.options.get(rule_for)  # type: ignore
            return eval(rule)
        except AttributeError:
            return 'None'

    def build_info_string(self) -> str:
        info_string = (f"; {self.book_date}={self.val_date}"
                       f": {self.debitor} --> {self.creditor}\n")
        for line in self.subject:
            info_string += f"; {line}\n"
        info_string += "; " + 60*"#" + "\n"
        return info_string

    def entry_template(self, options) -> str:
        """
        Template how to format ledger entry.
        """
        book_date = self.book_date
        val_date = self.val_date
        title = self.title
        creditor_acc = self.creditor_acc
        debitor_acc = self.debitor_acc
        currency = self.currency
        amount = self.amount
        ind = int(options.get('ledger_indent'))*" "
        if book_date == val_date:
            entry = f"{book_date} {title}\n"
        else:
            entry = f"{book_date}={val_date} {title}\n"
        if creditor_acc.startswith('[['):
            creditor_acc = eval(creditor_acc)
            for line in creditor_acc:
                amount_p = str(line[1]).replace(".", ",")
                entry += f"{ind}{line[0]}{ind}{currency} {amount_p}\n"
        else:
            entry += f"{ind}{creditor_acc}{ind}{currency} {amount}\n"
        entry += f"{ind}{debitor_acc}{ind}{currency} -{amount}"
        return entry

    def build_entry_string(self, options) -> str:
        """
        Tries to build reasonable ledger entry based on
        provided transfer data, defaults, and rules.
        Returns entry string based in 'entry_template'
        """
        account = options.get('account')
        import_rules = options.get('rules')

        def filter_rules(rules, key: str, val: str):
            """
            Returns list of dictionaries where key and val match
            or where key is missing.
            """
            matches = filter(lambda rule: rule.get(key, val) == val, rules)
            return list(matches)

        # exclude rules for other accounts
        account_rules = filter_rules(import_rules, 'account', account)

        # match for debitor
        matches_dbtr = filter_rules(account_rules, 'dbtr', self.debitor)
        if len(matches_dbtr) == 0:
            # no debitor match usually means: incoming from unknown source
            self.title = self.debitor
            self.creditor_acc = self.def_asset_acc
            self.debitor_acc = "Income:???"
            entry_string = self.entry_template(options)
        elif len(matches_dbtr) == 1:
            # usually income, potentially reimbursements etc.
            # can't be expense, because there usually are more rules that
            # match "myself" == dbtr
            match = matches_dbtr[0]
            self.title = match.get('title', self.creditor)
            self.debitor_acc = match.get('dbtr_acc')
            self.creditor_acc = match.get('cdtr_acc', self.def_asset_acc)
            entry_string = self.entry_template(options)
        else:
            # match for creditor
            matches_cdtr = filter_rules(matches_dbtr, 'cdtr', self.creditor)
            if len(matches_cdtr) == 0:
                # has to be unkonwn expense, otherwise
                self.creditor_acc = "Expenses:???"
                self.debitor_acc = self.def_asset_acc
                entry_string = self.entry_template(options)
            elif len(matches_cdtr) == 1:
                # known expense
                match = matches_cdtr[0]
                self.title = match.get('title', self.creditor)
                self.creditor_acc = match.get('cdtr_acc')
                self.debitor_acc = match.get('dbtr_acc', self.def_asset_acc)
                entry_string = self.entry_template(options)
            else:
                entry_string = ";\n; Multiple matches. Pick one\n"
                for match in matches_cdtr:
                    self.title = match.get('title', self.creditor)
                    self.creditor_acc = match.get('cdtr_acc')
                    self.debitor_acc = match.get(
                        'dbtr_acc', self.def_asset_acc)
                    entry_string += self.entry_template(options) + "\n"
        return entry_string


def main():
    options = get_updated_options(default_options)

    if options.get('reverse') == 'True':
        iterable = reversed(iterable_from_file(options))
    else:
        iterable = iterable_from_file(options)

    for raw_entry in iterable:
        e = Entry(raw_entry, options)
        info_string = e.build_info_string()
        entry_string = e.build_entry_string(options)
        combined = info_string + entry_string
        if options['dryrun'] is True:
            print(combined, "\n")
        else:
            edited = edit_string_with_editor(options, combined)
            append_to_ledger(options, edited)


if __name__ == "__main__":
    main()
