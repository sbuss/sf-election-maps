import pandas as pd


def parse_master_lookup(master_lookup_filename):
    """Parse the master lookup file, according to the 2018 format.

    The master lookup file provides a mapping from every record type (precinct,
    contest, candidate, tally-type) to a unique ID and description (plus other
    metadata).

    Args:
        master_lookup_filename: A path to the master lookup file, from SF
            department of elections.
    Returns a pandas dataframe with the master lookup information.
    """
    # The master lookup file has the following fixed-column-width format:
    # Field                 startcol stopcol fieldlen
    # Record_Type           1        10      10
    # Id                    11       17      7
    # Description           18       67      50
    # List_Order            68       74      7
    # Candidates_Contest_Id 75       81      7
    # Is_WriteIn            82       82      1
    # Is_Provisional        83       83      1
    #
    # More information can be found at
    # https://sfelections.org/results/20180605/data/BallotImageRCVhelp.pdf
    # https://sfelections.org/results/20180605/data/20180627/20180627_masterlookup.txt
    # https://sfelections.sfgov.org/june-5-2018-election-results-detailed-reports
    names = [
        # record_types = ['Precinct', 'Contest', 'Candidate', 'Tally Type']
        'Record_Type',
        'Id',
        'Description',
        'List_Order',
        'Candidates_Contest_Id',
        'Is_WriteIn',
        'Is_Provisional'
    ]
    widths = [10, 7, 50, 7, 7, 1, 1]
    lookup = pd.read_fwf(master_lookup_filename, widths=widths, names=names)
    return lookup


def parse_ballot_image(ballot_image_filename):
    """Parse the "ballot image" file, according to the 2018 format.

    The ballot image file contains all votes cast in all races for a given
    election. You will probably reference the columns 'Contest_Id' and
    'Candidate_Id' most frequently. The relevant values for those fields
    come from the master lookup file (see `master_lookup_filename`).

    Args:
        ballot_image_filename: A path to the ballot image file, from SF
            department of elections.
    Returns a pandas dataframe with the ballot image data.
    """
    # https://sfelections.org/results/20180605/data/20180627/20180627_ballotimage.txt

    # Field            startcol stopcol fieldlen
    # Contest_Id       1        7       7
    # Pref_Voter_Id    8        16      9
    # Serial_Number    17       23      7
    # Tally_Type_Id    24       26      3
    # Precinct_Id      27       33      7
    # Vote_Rank        34       36      3
    # Candidate_Id     37       43      7
    # Over_Vote        44       44      1
    # Under_Vote       45       45      1
    names = [
        'Contest_Id',
        'Pref_Voter_Id',
        'Serial_Number',
        'Tally_Type_Id',
        'Precinct_Id',
        'Vote_Rank',
        'Candidate_Id',
        'Over_Vote',
        'Under_Vote'
    ]
    widths = [7, 9, 7, 3, 7, 3, 7, 1, 1]
    kwargs = {}
    if ballot_image_filename.endswith('.gz'):
        kwargs = {'compression': 'gzip'}
    votes = pd.read_fwf(
        ballot_image_filename, widths=widths, names=names, **kwargs)
    return votes


def get_votes_for_contest(contest_name, master_lookup_df, ballot_image_df):
    contest_id = master_lookup_df[
        (master_lookup_df['Record_Type'] == 'Contest') &
        (master_lookup_df['Description'] == contest_name)]['Id'].values[0]
    return ballot_image_df[ballot_image_df['Contest_Id'] == contest_id]


def get_mayor_votes(master_lookup_df, ballot_image_df):
    return get_votes_for_contest('Mayor', master_lookup_df, ballot_image_df)


def get_supervisor_votes(district, master_lookup_df, ballot_image_df):
    contest_name = "Board of Supervisors, District %d" % district
    return get_votes_for_contest(
        contest_name, master_lookup_df, ballot_image_df)
