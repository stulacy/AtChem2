# -----------------------------------------------------------------------------
#
# Copyright (c) 2009 - 2012 Chris Martin, Kasia Boronska, Jenny Young,
# Peter Jimack, Mike Pilling
#
# Copyright (c) 2017 Sam Cox, Roberto Sommariva
#
# This file is part of the AtChem2 software package.
#
# This file is covered by the MIT license which can be found in the file
# LICENSE.md at the top level of the AtChem2 distribution.
#
# -----------------------------------------------------------------------------

# This script converts a chemical mechanism file in FACSIMILE format
# (.fac) into a Fortran-compatible format. The script generates five files in
# the model configuration directory:
# - mechanism.species
# - mechanism.reac
# - mechanism.prod
# - mechanism.ro2
# - mechanism.f90
#
# Acknowledgements: B. Nelson, M. Newland
#
# ARGUMENTS:
# - path to the .fac file
# - path to the model configuration directory [default: model/configuration/]
# - path to the MCM data files directory [default: mcm/]
# ---------------------------------------------- #
from __future__ import print_function
import sys
import re
import os
import fix_mechanism_fac

reservedSpeciesList = ['N2', 'O2', 'M', 'RH', 'H2O', 'BLHEIGHT', 'DEC', 'JFAC', 'DILUTE', 'ROOF', 'ASA', 'RO2']
reservedOtherList = ['EXP', 'TEMP', 'PRESS', 'LOG10', 'T', 'J']


## ------------------------------------------------------------------ ##


def tokenise_and_process(input_string, variablesDict):
    """
    This function takes in a single string, and a dictionary of known variables from previous lines,
    and returns the same string but with known variables replaced by a reference to their matching
    element in a vector q. This removes the dependence on potentially 100+ named variables, and
    replaces them with a single vector.

    :param input_string: this should be a string. Its contents will be used as the basis of the return string.
    :param variableDict: this is a Dictionary containing all the known variables up to this pointself.
    :returns new_rhs: a string based on input_string, but with references to known variables replaced by
      references to elements in the vector q.
    """

    assert isinstance(input_string, str), 'tokenise_and_process: input_string is not of type str: ' + str(input_string)
    assert isinstance(variablesDict, dict), 'tokenise_and_process: variablesDict is not of type dict: ' + str(variablesDict)

    # Generate start and end points of sections of symbols and nonsymbols
    symbol_regex = '[()\-+*@/ ]+'
    nonsymbol_regex = '[^()\-+*@/ ]+'
    list_of_symbol_starts = [m.start(0) for m in re.finditer(symbol_regex, input_string)]
    list_of_symbol_ends = [m.end(0) for m in re.finditer(symbol_regex, input_string)]
    list_of_nonsymbol_starts = [m.start(0) for m in re.finditer(nonsymbol_regex, input_string)]
    list_of_nonsymbol_ends = [m.end(0) for m in re.finditer(nonsymbol_regex, input_string)]
    new_rhs = ''

    # Now that the symbol/non-symbol sections are identified, we need to create the new string by recombining otherwise
    # sections in the right order, with some replaced by q(i) syntax.
    #
    # Recombine the lists in the right order, but replace the nonsymbols that aren't numbers, reserved words or reserved species
    # (and thus must be new species/intermediate values) with q(i) notation.
    #
    # Loop while there are any substrings left
    while list_of_symbol_starts != [] or list_of_nonsymbol_starts != []:
        # We should use the next symbol if either
        #    1) both lists are non-empty and the symbols list has a lower first element, or
        #    2) only the symbols list has anything left in it
        if ((list_of_symbol_starts != [] and list_of_nonsymbol_starts != []) and list_of_symbol_starts[0] < list_of_nonsymbol_starts[0]) \
          or (list_of_symbol_starts != [] and list_of_nonsymbol_starts == []):
            # add next symbol
            # Print the substring as-is
            new_rhs += input_string[list_of_symbol_starts[0]:list_of_symbol_ends[0]]
            # Remove the indices of this substring from the lists
            del list_of_symbol_starts[0]
            del list_of_symbol_ends[0]
        else: # This will execute if there are only non-symbols left, or if the non-symbols list has a lower first element.
            # add next nonsymbol
            # Get the substring of interest
            varname = input_string[list_of_nonsymbol_starts[0]:list_of_nonsymbol_ends[0]]
            # If it's not a number or a reserved word, it must be a variable, so substitute with the relevant element from q.
            if not re.match('^[0-9]', varname) and varname not in reservedSpeciesList and varname not in reservedOtherList:
                new_rhs += 'q(' + str(variablesDict[varname]) + ')'
            # Otherwise, just print the substring as-is
            else:
                new_rhs += input_string[list_of_nonsymbol_starts[0]:list_of_nonsymbol_ends[0]]
            # Remove the indices of this substring from the lists
            del list_of_nonsymbol_starts[0]
            del list_of_nonsymbol_ends[0]

    # Return the reconstructed string
    return new_rhs


def convert(input_file, mech_dir, mcm_dir):
    """
    This is the main function of this file. It takes as input a chemical mechanism file (.fac), and from it generates
    5 files for use by AtChem2's Fortran code:

    - 'Generic Rate Coefficients' and 'Complex reactions' go to mech_dir/mechanism.f90 with little more than formatting
      changes - each line is replicated in full but with each named rate converted to an element in the vector q.
    - The rates defined in 'Reaction definitions' also go to mech_dir/mechanism.f90 as elements of the vector p.
    - The species involved as reactants (respectively products) in reactions in 'Reaction definitions' are split up into individual
      species, and their species and reactions numbers go to mechanism.reac (respectively mechanism.prod). Combining
      mechanism.reac, mechanism.prod and the last section of mech_dir/mechanism.f90 gives the original information
      contained in 'Reaction definitions' but in the format that AtChem2 can parse.
    - The numbers and names of all species encountered go to mechanism.species.
    - The numbers and names of all RO2 species in 'Peroxy radicals' end up in mechanism.ro2.

    :param input_file: string containing a relative or absolute reference to the .fac file to be processed.
    :param mech_dir: string containing a relative or absolute reference to the directory in which the function should
      place mechanism.f90, and where the environmentVariables.config file should be read from.
      This is normally model/configuration.
    :param mech_dir: string containing a relative or absolute reference to the directory in which the function should
      place mechanism.{prod,reac,ro2,species}. This is normally model/configuration/ for the given model.
    :param mcm_dir: string containing a relative or absolute reference to the directory housing the reference file peroxy-radicals_v3.3.1.
      This is normally mcm/
    """

    # Work out the values of directory and filename of input_file, and check their existence.
    input_directory = os.path.dirname(os.path.abspath(input_file))
    input_filename = os.path.basename(input_file)
    assert os.path.isfile(os.path.join(input_directory, input_filename)), 'The input file ' + str(
        os.path.join(input_directory, input_filename)) + ' does not exist.'
    print(input_directory)

    # Fix the input contents of any errant newlines
    fix_mechanism_fac.fix_fac_full_file(os.path.join(input_directory, input_filename))

    # Read in the input file
    print('Reading input file')
    with open(os.path.join(input_directory, input_filename), 'r') as input_file:
        s = input_file.readlines()

    # split the lines into the following sections:
    # - Ignore everything up to Generic Rate Coefficients
    # - Generic Rate Coefficients
    # - Complex reactions
    # - Peroxy radicals
    # - Reaction definitions
    section_headers_indices = [0, 1, 2, 3]
    section_headers = ['Generic Rate Coefficients', 'Complex reactions', 'Peroxy radicals', 'Reaction definitions']
    generic_rate_coefficients = []
    complex_reactions = []
    peroxy_radicals = []
    reaction_definitions = []

    section = 0
    for line in s:
        for header_index in section_headers_indices:
            if section_headers[header_index] in line:
                section += 1
        if section == 1:
            generic_rate_coefficients.append(line)
        elif section == 2:
            complex_reactions.append(line)
        elif section == 3:
            peroxy_radicals.append(line)
        elif section == 4:
            reaction_definitions.append(line)
        else:
            assert section == 0, "Error, section is not in [0,4]"


    # Convert peroxy_radicals to a list of strings, each of the RO2 species from 'Peroxy radicals'
    ro2List = []
    for item in peroxy_radicals:
        if not re.match('\*', item):
            # We have an equals sign on the first line. Handle this by splitting against =, then taking the last element of the
            # resulting list, which will either be the right-hand side of the first line, or the whole of any other line.
            # Similarly, the final line will end with a colon. Handle in a similar way.
            # Then split by +. Append each item to ro2_input: multiple appends use 'extend'
            ro2List.extend([elem.strip() for elem in item.split('=')[-1].split(';')[0].strip().split('+')])
    # Remove empty strings
    ro2List = list(filter(None, ro2List))


    # Read in the reference RO2 species from the peroxy-radicals_v3.3.1 file
    with open(os.path.join(mcm_dir, 'peroxy-radicals_v3.3.1'), 'r') as RO2List_file:
        RO2List_reference = [r.rstrip() for r in RO2List_file.readlines()]

    # Check each of the RO2s from 'Peroxy radicals' are in the reference RO2 list. If not print a warning at the top of
    # mechanism.f90 for each errant species.
    # TODO: This will break the exected format when mechanism.f90 is replaced by a parsable format.
    print('looping over inputted RO2s')

    with open(os.path.join(mech_dir, 'mechanism.f90'), 'w') as mech_rates_file:
        mech_rates_file.write("""! Note that this file is automatically generated by build/mech_converter.py -- Any manual edits to this file will be overwritten when calling build/mech_converter.py
""")
        for ro2_species in [element for  element in ro2List if element not in RO2List_reference]:
            print(' ****** Warning: ' + ro2_species + ' NOT found in the reference RO2 list ****** ')
            mech_rates_file.write('! ' + ro2_species +
                                  ' is not in the MCM list of RO2 species. Should it be in the RO2 sum?\n')

    # Identify whether dilution is in use
    dilute = False
    with open(mech_dir + '/environmentVariables.config') as env_var_file:
        environmentVariables = env_var_file.readlines()
        for x in environmentVariables:
            x = x.split()

            try:
                if x[1] == "DILUTE" and x[2] != "NOTUSED":
                    dilute = x[2]

            except IndexError:
                continue

    # Initialise list, dictionary and a counter.
    mechanism_rates_coeff_list = []
    variablesDict = dict()
    reactionNumber = 0
    # Process sections 1 and 2
    # - copy comment lines across
    # - other lines are reformatted to be Fortran syntax, then its contents edited to convert individual
    #   rate names to elements in a vector q.
    for line in generic_rate_coefficients + complex_reactions:
        # Check for comments (beginning with a !), or blank lines
        if (re.match('!', line) is not None) or (line.isspace()):
            mechanism_rates_coeff_list.append(line)
        # Check for lines starting with either ; or *, and write these as comments
        elif (re.match(';', line) is not None) or (re.match('[*]', line) is not None):
            mechanism_rates_coeff_list.append('!' + line)
        # Otherwise assume all remaining lines are in the correct format, and so process them
        else:
            # reactionNumber keeps track of the line we are processing
            reactionNumber += 1

            # This matches anything like @-dd.d and replaces with **(-dd.d). This uses (?<=@) as a lookbehind assertion,
            # then matches - and any combination of digits and decimal points. This replaces the negative number by its
            # bracketed version.
            # It also then converts all @ to ** etc.
            line2 = re.sub('(?<=@)-[0-9.]*',
                           '(\g<0>)',
                           line.replace(';', '').strip()
                           ).replace('@', '**')
            # Append _DP to the end of all digits that aren't followed by more digits or letters (targets a few too many)
            line2 = re.sub('[0-9]+(?![a-zA-Z0-9\.])',
                           '\g<0>_DP',
                           line2)
            # Undo the suffix _DP for any species names and for LOG10
            line2 = re.sub(r'\b(?P<speciesnames>[a-zA-Z][a-zA-Z0-9]*)_DP',
                           '\g<speciesnames>',
                           line2)
            # Undo the suffix _DP for any numbers like 1D7 or 2.3D-8
            line2 = re.sub(r'\b(?P<doubles1>[0-9][0-9\.]*)[dDeE](?P<doubles2>[+-]*[0-9]+)_DP',
                           '\g<doubles1>e\g<doubles2>_DP',
                           line2)
            # Add .0 to any literals that don't have a decimal place - this is necessary as it seems you can't use extended
            # precision on such a number - gfortran complains about an unknown integer kind, when it should really be a real kind
            line2 = re.sub(r'(?<![\.0-9+-dDeE])(?P<doubles>[0-9]+)_DP',
                           '\g<doubles>.0_DP',
                           line2)

            # strip whitespace, ; and %
            cleaned_line = line2.strip().strip('%;').strip()

            # Process the assignment: split by = into variable names and values
            [lhs, rhs] = re.split('=', cleaned_line)

            # Strip each.
            variable_name = lhs.strip()
            value = rhs.strip()

            # TODO: check for duplicates
            variablesDict[variable_name] = reactionNumber

            # Replace any variables declared here with references to q, with each new variable assigned
            # to a new element of q.
            new_rhs = tokenise_and_process(value, variablesDict)

            # Save the resulting string to mechanism_rates_coeff_list
            mechanism_rates_coeff_list.append('q('+str(variablesDict[variable_name]) + ') = ' + new_rhs + '  !' + cleaned_line + '\n')

    # Save the number of such equations to be output to mechanism.{prod,reac}
    numberOfGenericComplex = reactionNumber


    # Initialise a few variables
    speciesList = []
    rateConstants = []
    reactionNumber = 0
    # Process 'Reaction definitions'. We process this before 'Peroxy radicals' because that relies on our
    # SpeciesList generated here.
    # - copy comment lines across
    # - other lines are split into their consituent parts:
    #   - rateConstants are the reaction rates; these are processed via reformatting and tokenisation to use the vector q where needed.
    #   - the reactants and products of each species are collected up, numbered as necessary, and their placements output to mechanism.{prod,reac,species}
    mech_reac_list = []
    mech_prod_list = []
    # Loop over all lines in the reaction_definitions section of the input file
    for line in reaction_definitions:

        # Check for comments (beginning with a !), or blank lines
        if (re.match('!', line) is not None) or (line.isspace()):
            rateConstants.append(line)
        # Check for lines starting with either ; or *, and write these as comments
        elif (re.match(';', line) is not None) or (re.match('[*]', line) is not None):
            rateConstants.append('!' + line)
        # Otherwise assume all remaining lines are in the correct format, and so process them
        else:
            # reactionNumber keeps track of the line we are processing
            reactionNumber += 1

            # strip whitespace, ; and %
            line = line.strip().strip('%;').strip()

            # split by the semi-colon : lhs is reaction rate, rhs is reaction equation
            [lhs, rhs] = re.split(':', line)

            # Add reaction rate to rateConstants
            rateConstants.append(lhs)

            # Process the reaction: split by = into reactants and products
            [reactantsList, productsList] = re.split('=', rhs)

            # Process each of reactants and products by splitting by +. Strip each at this stage.
            reactants = [item.strip() for item in re.split('[+]', reactantsList)]
            products = [item.strip() for item in re.split('[+]', productsList)]

            # Ignore empty reactantsList
            if not reactantsList.strip() == '':
                # Compare each reactant against known species.
                reactantNums = []
                for x in reactants:
                    # If the reactant is a known species then add its number to reactantNums
                    if x in speciesList:
                        reactantNums.append(speciesList.index(x)+1)
                    else:
                        # Reactant x is not a known species.
                        # Add reactant to speciesList, and add this number to
                        # reactantNums to record this reaction.
                        speciesList.append(x)
                        reactantNums.append(len(speciesList))

                # Write the reactants to mech_reac_list
                mech_reac_list.extend([str(reactionNumber) + ' ' + str(z) + '\n' for z in reactantNums])

            # Ignore empty productsList
            if not productsList.strip() == '':
                # Compare each product against known species.
                productNums = []
                for x in products:
                    # If the reactant is a known species then add its number to reactantNums
                    if x in speciesList:
                        productNums.append(speciesList.index(x)+1)
                    else:
                        # Product x is not a known species.
                        # Add product to speciesList, add this number to
                        # productNums to record this reaction.
                        speciesList.append(x)
                        productNums.append(len(speciesList))

                # Write the products to mechanism.prod
                mech_prod_list.extend([str(reactionNumber) + ' ' + str(z) + '\n' for z in productNums])

    # Write out species for reactions to implement DILUTE factor if it's not NOTUSED.
    if dilute:
        for spec in speciesList:
            reactionNumber += 1
            mech_reac_list.append(str(reactionNumber) + ' ' + str(speciesList.index(spec) + 1) + '\n')

    with open(os.path.join(mech_dir, 'mechanism.prod'), 'w') as prod_file:
        # Output number of species and number of reactions
        prod_file.write(str(len(speciesList)) + ' ' + str(reactionNumber) + ' ' + str(numberOfGenericComplex) + ' numberOfSpecies numberOfReactions numberOfGenericComplex\n')
        # Write all other lines
        for line in mech_prod_list:
            prod_file.write(line)

    with open(os.path.join(mech_dir, 'mechanism.reac'), 'w') as reac_file:
        # Output number of species and number of reactions
        reac_file.write(str(len(speciesList)) + ' ' + str(reactionNumber) + ' ' + str(numberOfGenericComplex) + ' numberOfSpecies numberOfReactions numberOfGenericComplex\n')
        # Write all other lines
        for line in mech_reac_list:
            reac_file.write(line)

    # Write speciesList to mechanism.species, indexed by (1 to len(speciesList))
    with open(os.path.join(mech_dir, 'mechanism.species'), 'w') as species_file:
        for i, x in zip(range(1, len(speciesList) + 1), speciesList):
            species_file.write(str(i) + ' ' + str(x) + '\n')


    # Write out rate coefficients
    i = 0
    mech_rates_list = []
    for rate_counter, x in zip(range(len(s)), rateConstants):
        if (re.match('!', x) is not None) | (x.isspace()):
            mech_rates_list.append(str(x))
        else:
            # This matches anything like @-dd.d and replaces with **(-dd.d). This uses (?<=@) as a lookbehind assertion,
            # then matches - and any combination of digits and decimal points. This replaces the negative number by its
            # bracketed version.
            i += 1
            string = re.sub('(?<=@)-[0-9.]*', '(\g<0>)', x)
            # Now convert all @ to ** etc.
            string = string.replace('@', '**')
            string = string.replace('<', '(')
            string = string.replace('>', ')')
            # Replace any float-type numbers (xxx.xxxE+xx) with double-type - (xxx.xxxD+xx)
            string = re.sub(r'(?P<single>[0-9]+\.[0-9]+)[eE]',
                           '\g<single>D',
                           string)
            mech_rates_list.append('p(' + str(i) + ') = ' + \
              tokenise_and_process(string, variablesDict) + '  !' + reaction_definitions[rate_counter])

    # Write out further reactions to implement DILUTE factor if it's not NOTUSED.
    if dilute:
        for _ in speciesList:
            i += 1
            mech_rates_list.append('p(' + str(i) + ') = DILUTE ! DILUTE\n')

    # Combine mechanism rates and RO2 sum files
    with open(os.path.join(mech_dir, 'mechanism.f90'), 'a') as mech_rates_coeff_file:
        mech_rates_coeff_file.write("""
module mechanism_mod
    use, intrinsic :: iso_c_binding
    implicit none

contains

    subroutine update_p(p, q, TEMP, N2, O2, M, RH, H2O, BLHEIGHT, DEC, JFAC, DILUTE, ROOFOPEN, ASA, J, RO2) bind(c,name='update_p')

        integer, parameter :: DP = selected_real_kind( p = 15, r = 307 )
           real(c_double), intent(inout) :: p(*), q(*)
        real(c_double), intent(in) :: TEMP, N2, O2, M, RH, H2O, BLHEIGHT, DEC, JFAC, DILUTE, ROOFOPEN, ASA, J(*), RO2
        """)
        # Write out Generic Rate Coefficients and Complex reactions
        for item in mechanism_rates_coeff_list:
            mech_rates_coeff_file.write(item)
        # Write out Reaction definitions
        for r in mech_rates_list:
            mech_rates_coeff_file.write(r)
        mech_rates_coeff_file.write("""
    end subroutine update_p
end module mechanism_mod
""")


    # Finally, now that we have the full species list, we can output the RO2s to mechanism.ro2
    # loop over RO2 and write the necessary line to mechanism.ro2, using the species number of the RO2
    print('adding RO2 to ' + mech_dir + '/mechanism.ro2')
    with open(os.path.join(mech_dir, 'mechanism.ro2'), 'w') as ro2_file:
        ro2_file.write("""! Note that this file is automatically generated by build/mech_converter.py -- Any manual edits to this file will be overwritten when calling build/mech_converter.py
""")

        for ro2List_i in ro2List:
            for speciesNumber, y in zip(range(1, len(speciesList) + 1), speciesList):
                if ro2List_i.strip() == y.strip():
                    ro2_file.write(str(speciesNumber) + ' !' + ro2List_i.strip() + '\n')
                    # Exit loop early if species found
                    break
            # This code only executes if the break is NOT called, i.e. if the loop runs to completion without the RO2 being
            # found in the species list
            else:
                error_message = ''.join([
                  ' ****** ',
                  'Error: RO2 species "',
                  str(ro2List_i.strip()),
                  '" NOT found in the mechanism. Please check the RO2 section',
                  ' of your mechanism file for incorrect species names!',
                  ' ******'])
                raise RuntimeError(error_message)


## ------------------------------------------------------------------ ##


def main():
    assert len(sys.argv) > 1, 'Please enter a filename as argument, pointing to the chemical mechanism file (.fac ):'
    input_filename = sys.argv[1]
    # mech_dir defaults to '.' if not given
    if len(sys.argv) <= 2:
        mech_dir = './model/configuration/'
    else:
        mech_dir = sys.argv[2]
    if len(sys.argv) <= 3:
        mcm_dir = './mcm/'
    else:
        mcm_dir = sys.argv[3]

    # check the locations supplied exist
    assert os.path.isfile(input_filename), 'Failed to find file ' + input_filename
    assert os.path.exists(mech_dir), 'Failed to find directory ' + mech_dir
    assert os.path.exists(mcm_dir), 'Failed to find directory ' + mcm_dir

    # call conversion function
    convert(input_filename, mech_dir, mcm_dir)


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as e:
        print(str(e))
        sys.exit(os.EX_DATAERR)
