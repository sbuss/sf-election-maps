from collections import namedtuple

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
    # https://sfelections.org/results/20180605/data/BallotImageRCVhelp.pdf
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


RcvRound = namedtuple(
    "RcvRound",
    ["name", "votes", "num_undervotes", "num_overvotes", "dropped_candidate"])

def run_rcv_for_contest(
        contest_name, master_lookup_df, ballot_image_df, threshold=0.5):
    """Run RCV elimination for a given contest.

    Returns a tuple of a list of dataframes with the votes redistributed. The
    0th dataframe is all votes (1st dataframe is after the first round, etc),
    and the winner candidate id.
    """
    votes = get_votes_for_contest(
        contest_name, master_lookup_df, ballot_image_df)
    votes = votes.copy(deep=True)
    # Rules:
    # 1. Eliminate last place and redistribute votes until one candidate has
    #    > threshold votes.
    # 2. If a redistributed vote goes to an eliminated candidate, discard and
    #    try again.
    # 3. Overvotes invalidate a ballot but only if reached. For example, voting
    #    for one person in first choice, and two people in second choice only
    #    invalidates it if the first choice is eliminated.
    # 4. Undervotes get skipped over, they're treated very similarly to
    #    already-eliminated candidates. An undervote is a blank choice.
    # 5. When a ballot gets redistributed and the next choice is an
    #    already-eliminated candidate, do not assign the ballot to that
    #    candidate, but skip that choice and do the next one.
    # 6. When the next choice is the same candidate (eg Alice #1, Alice #2,
    #    Alice #3), skip them as in #5.

    exhausted = set()
    # The data looks like this:
    # Id      Contest_Id  Pref_Voter_Id   Precinct_Id Vote_Rank   Candidate_Id    Over_Vote   Under_Vote
    # 762048  21          13525           281         1           188             0           0
    # 762049  21          13525           281         2           0               0           1
    # 762050  21          13525           281         3           0               0           1
    # 762051  21          13526           281         1           188             0           0
    # 762052  21          13526           281         2           186             0           0
    # 762053  21          13526           281         3           0               0           1
    # That means voter 13525 voted *only* for candidate 188, while voter 13526
    # voted for candidates 188 #1 and 186 #2.
    winner = None

    # The zeroth round is the input data
    rounds = [RcvRound("Original", votes, 0, 0, None)]
    # First remove all completely undervoted ballots. That's people who didn't
    # vote for anyone at all.
    _is_all_undervote = votes.groupby('Pref_Voter_Id')['Under_Vote'].all()
    all_undervote_voter_ids = _is_all_undervote[_is_all_undervote].index
    votes = votes[~votes.Pref_Voter_Id.isin(all_undervote_voter_ids)]
    # The first round is all-undervotes dropped
    rounds.append(
        RcvRound("Round 0", votes, len(all_undervote_voter_ids), 0, None))

    # Start the ranking
    while not winner:
        print("Round %d" % (len(rounds) - 1))
        keep_going = True
        num_undervotes = 0
        num_overvotes = 0
        eliminated = None
        while keep_going:
            keep_going = False
            # Look at the highest rank vote for each voter.
            top_votes = \
                votes.sort_values('Vote_Rank').groupby('Pref_Voter_Id').first()

            # If the top choice is an undervote, drop it and keep going
            undervotes = top_votes[top_votes['Under_Vote'] == 1]
            if len(undervotes) > 0:
                num_undervotes += len(undervotes)
                print("%d undervotes" % len(undervotes))
                keep_going = True
                
                ## Slowest method
                #ir = undervotes.iterrows()
                #row = ir.next()
                #x = votes[(votes.Pref_Voter_Id == row[0]) &
                #          (votes.Vote_Rank == row[1].Vote_Rank)]
                #for row in ir:
                #    x = x | votes[(votes.Pref_Voter_Id == row[0]) &
                #                  (votes.Vote_Rank == row[1].Vote_Rank)]
                #votes = votes.drop(x.index, axis=0)

                # Fast method of the above
                idxs = [(row[0], row[1].Vote_Rank)
                        for row in undervotes.iterrows()]
                drop_idxs = votes.reset_index().set_index(
                    ["Pref_Voter_Id", "Vote_Rank"]).loc[idxs]["index"].values
                votes = votes.drop(drop_idxs, axis=0)

            overvotes = top_votes[top_votes['Over_Vote'] == 1]
            if len(overvotes) > 0:
                num_overvotes += len(overvotes)
                print("%d overvotes" % len(overvotes))
                keep_going = True
                # Mark all these voters as exhausted
                # Note that overvotes' index is Pref_Voter_Id
                exhausted |= set(overvotes.index)
                # And remove those voters from the set of votes
                votes = votes[~votes['Pref_Voter_Id'].isin(exhausted)]

        # And count those votes by candidate
        candidate_votes = \
            top_votes.groupby('Candidate_Id').count().sort_values('Vote_Rank')

        total_votes = candidate_votes.sum()['Vote_Rank']
        top_vote_count = candidate_votes.iloc[
            len(candidate_votes) - 1]['Vote_Rank']
        if top_vote_count * 1.0 / total_votes > threshold:
            winner = candidate_votes.index[len(candidate_votes) - 1]
        else:
            # eliminate last place and redistribute
            eliminated = candidate_votes.index[0]
            votes = votes[votes['Candidate_Id'] != eliminated]
        rounds.append(
            RcvRound("Round %d" % (len(rounds) - 1), top_votes, num_undervotes,
                num_overvotes, eliminated))
    return rounds, winner

def pretty_print_rcv_rounds(contest_name, master_lookup_df, rcv_rounds):
    contest_id = master_lookup_df[
        (master_lookup_df['Record_Type'] == 'Contest') &
        (master_lookup_df['Description'] == contest_name)]['Id'].values[0]
    id_to_candidate_name = dict(
        master_lookup_df[
            master_lookup_df['Candidates_Contest_Id'] == contest_id][
                ['Id', 'Description']].values)

    last_votes = {}
    for rnd in rcv_rounds[0][2:]:
        print(rnd.name)
        id_to_vote_counts = dict(
            rnd.votes.groupby('Candidate_Id')['Contest_Id'].count())
        if not last_votes:
            last_votes = id_to_vote_counts
        total = sum(id_to_vote_counts.values())
        for (vid, cnts) in sorted(id_to_vote_counts.iteritems()):
            last_vote = last_votes.get(vid, 0)
            last_vote_display = ""
            if last_vote != cnts:
                last_vote_display = "+%d" % (cnts - last_vote)
            print("%30s %7d %6s %5.2f%%" %
                (id_to_candidate_name[vid],
                    cnts,
                    last_vote_display,
                    cnts * 100.0 / total))
            last_votes[vid] = cnts
        print
