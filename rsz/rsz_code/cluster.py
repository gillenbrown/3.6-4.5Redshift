import os

from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import numpy as np

import model
from source import Source
import data
import plotting
import config


class Cluster(object):
    """
    Class that holds the data about a cluster, and that does the redshift
    fitting.
    """

    # Keeping the predictions for the red sequence with the cluster object
    # made things a lot easier. And since the predictions are the same for
    # all cluster, this is a class variable rather than an instance variable.
    models = model.model_dict(0.01)

    def __init__(self, filepath, params):
        self.name = self._name(filepath, params["extension"])

        # I'll initialize empty source list, that will be filled as we go
        self.sources_list = []
        self.z = dict()
        self.flags = dict()

        self.figures = []

        # then read in the objects in the catalog
        self.read_catalog(filepath, params)

    @staticmethod
    def _name(filepath, extension):
        filename = os.path.split(filepath)[-1]
        # just remove the extension from the filename
        return filename.rstrip(extension)

    def read_catalog(self, filepath, params):
        """ Read the catalog, parsing things into sources.

        This function calls other functions to do the dirty work.

        :param filepath: path of the catalog to be parsed.
        :param params: parameter dictionary
        :return: none, but the cluster's source list variable is populated.
        """
        with open(filepath) as cat:
            for line in cat:
                # some catalog formats aren't formatted the way I'd like (the
                # column headers aren't commented out), so ignore that line.
                if not line.startswith("#") and \
                        not line.strip().startswith("id"):
                    # split the line, to make for easier parsing.
                    split_line = [self.to_float(i) for i in line.split()]

                    # get the various things from the parser functions.
                    ra, dec = self.get_ra_dec(params, split_line)
                    mags = self.get_mags(params, split_line)
                    dist = self.get_dist(params, split_line)

                    # check that the user has specified the appropriate things.
                    if ra is None and dec is None and dist is None:
                        raise TypeError("Specify one of either ra/dec or dist")

                    # turn this info into a source object, then add it.
                    this_source = Source(ra, dec, mags, dist)
                    self.sources_list.append(this_source)

    @staticmethod
    def to_float(item):
        """If an item can be converted to a float, it will be. If not, the item
        will be returned unchanged.

        :param item: Item to potentially convert to a float.
        :return: the item, potentially converted to a float.
        """
        try:
            return float(item)
        except ValueError:  # That's the error from a failed float conversion.
            return item

    @staticmethod
    def get_ra_dec(params, split_line):
        """Parses the line to get the ra and dec.

        If the user doesn't specify ra and dec, then return None.

        :param params: Parameter dictionary that is passed all around the code.
        :param split_line: Line of the catalog split into the components.
        :return: ra and dec as a tuple
        """
        if params['ra'] != "-99" and params["dec"] != "-99":
            ra = split_line[int(params["ra"])]
            dec = split_line[int(params["dec"])]
        else:
            ra, dec = None, None
        return ra, dec

    @staticmethod
    def get_mags(params, split_line):
        """ Parses the config file to get the magnitudes.

        :param params: Parameter dictionary that is passed all around the code.
        :param split_line: Line of the catalog split into the components.
        :return: ch1, ch2, ch1-ch2. Each will be in AB mags, and returned as
                 a data object, to include the errors.
        """
        # check that they did the type and mags right
        if params["type"] not in ["mag", "flux"] or \
           params["mag_system"] not in ["vega", "ab"]:
            raise TypeError("Either type or mags wasn't specified correctly"
                            "in the parameter file.")

        # see which bands were specified in the param file
        non_band_params = ["catalog_directory", "extension",
                           "plot_directory", "results_file", "rs_catalog_dir",
                           "type", "mag_zeropoint", "mag_system", "ra", "dec",
                           "dist", "CMD", "fitting_procedure", "final_CMD",
                           "location", "interactive"]

        bands = []
        for key in params:
            if key in non_band_params:
                continue
            # the key we have is either a flux/mag or an error
            if not key.endswith("_err"):
                bands.append(key)

        mags = dict()
        for band in bands:
            band_idx = int(params[band])
            band_err_idx = int(params[band + "_err"])

            band_data = split_line[band_idx]
            band_data_err = split_line[band_err_idx]

            # convert fluxes to magnitudes if need be
            if params["type"] == "flux":

                if band_data == 0:
                    # give it a slightly negative flux, which will be
                    # interpreted as a bad mag
                    band_data = -0.1
                # calculate magerr first, since we need to use the flux
                band_data_err = Cluster.percent_flux_errors_to_mag_errors(
                    band_data_err / band_data)
                # print band_data
                band_data = Cluster.flux_to_mag(band_data,
                                                float(params["mag_zeropoint"]))


            # Convert to AB mags if needed. If we used flux, they are already in AB
            if params["type"] == "mag" and params["mag_system"] == "vega":
                try:
                    band_data += config.vega_to_ab(band)
                except KeyError:
                    raise KeyError("Please specify the AB/Vega conversion "
                                   "for {} in config.py.".format(band))

            # convert to Data type, and add to dictionary
            mags[band] = data.Data(band_data, band_data_err)

        return mags

    @staticmethod
    def get_dist(params, split_line):
        """Parse the line to get the distance from center.

        :param params: Parameter dictionary that is passed all around the code.
        :param split_line: Line of the catalog split into the components.
        :return: The distance of the object from the cluster center.
        """
        if params["dist"] != "-99":
            return split_line[int(params["dist"])]
        else:
            return None

    @staticmethod
    def flux_to_mag(flux, zeropoint):
        """Convert flux to magnitude with the given zeropoint.

        :param flux: flux in whatever units. Choose your zeropoint correctly
                     to make this work with the units flux is in.
        :param zeropoint: zeropoint of the system (in mags).
        :return: magnitude that corresponds to the given flux. If flux is
                 negative, -99 is returned.
        """
        if flux <= 0:
            return -99
        return -2.5 * np.log10(flux) + zeropoint

    @staticmethod
    def percent_flux_errors_to_mag_errors(percent_flux_error):
        """Converts a percentage flux error into a magnitude error.

        m = -2.5 log10(F) + C
        dm = -2.5/(ln(10)) dF/F

        :param percent_flux_error: percentage flux error
        :return: magnitude error corresponding to the percentage flux error.
        """
        if percent_flux_error < 0:
            return 99
        return (2.5 / np.log(10)) * percent_flux_error

    def __repr__(self):
        return self.name

    def fit_z(self, params, cfg):
        """
        Find the redshift of the cluster by matching its red sequence the
        red sequence models produced by EzGal. This is the main
        functionality of the entire code.

        :param params: Dictionary full of the user's parameters for the
                       program from the config file.
        :param color: Color combination use to fit the RS.
        :return: redshift of the cluster. Will be an AsymmetricData
                 instance, to account for the possibility of different upper
                 and lower limits on the redshift.
        """

        # do a location cut, to only focus on galaxies near the center of
        # the image.
        self._location_cut(1.5)

        # we need to initialize the flags for the cluster
        self.flags[cfg["color"]] = 0

        # If the user wants, plot the initial CMD with predictions
        if params["CMD"] == "1":
            fig, ax = plt.subplots(figsize=(9, 6))
            ax = plotting.cmd(self, ax, cfg)
            vc_ax, vmax = plotting.add_vega_labels(ax, cfg)
            plotting.add_all_models(fig, ax, steal_axs=[ax, vc_ax, vmax],
                                    cfg=cfg)
            self.figures.append(fig)

        # Do a quick and dirty initial redshift fitting, to get a starting
        # point.
        self.z[cfg["color"]] = self._initial_z(cfg)

        # If the user wants to see this initial fit, plot it.
        if params["fitting_procedure"] == "1":
            # set up the plot
            fig, ax = plt.subplots(figsize=(9, 6))
            ax = plotting.cmd(self, ax, cfg)
            plotting.add_vega_labels(ax, cfg)
            plotting.add_one_model(ax, self.models[cfg["color"]]
                                                  [self.z[cfg["color"]].value],
                                   "k")
            plotting.add_redshift(ax, self.z[cfg["color"]].value)
            self.figures.append(fig)


        # do iterations of fitting, each with a progressively smaller
        # color cut, which is designed to hone in on the red sequence.
        for bluer_cut, redder_cut in zip(cfg["bluer_color_cut"],
                                         cfg["redder_color_cut"]):
            # set red sequence members based on the cuts
            self._set_rs_membership(self.z[cfg["color"]].value,
                                    bluer_cut, redder_cut,
                                    cfg["brighter_mag_cut"],
                                    cfg["dimmer_mag_cut"],
                                    cfg)

            # do the chi-squared fitting.
            self.z[cfg["color"]] = self._chi_square_w_error(cfg)

            # if the user wants, plot the procedure
            if params["fitting_procedure"] == "1":
                fig, ax = plt.subplots(figsize=(9, 6))
                ax = plotting.cmd(self, ax, cfg)
                plotting.add_vega_labels(ax, cfg)
                plotting.add_one_model(ax, self.models[cfg["color"]]
                                                      [self.z[cfg["color"]].value],
                                       "k")
                plotting.add_redshift(ax, self.z[cfg["color"]].value)
                self.figures.append(fig)

        # See if there is a cloud, rather than a red sequence.
        self._clean_rs_check(cfg)

        # Set the final red sequence members
        self._set_rs_membership(self.z[cfg["color"]].value,
                                cfg["final_rs_color"][0],
                                cfg["final_rs_color"][1],
                                cfg["final_rs_mag"][0],
                                cfg["final_rs_mag"][0],
                                cfg)

        # and do the location check based on these RS values
        self._location_check(cfg["color"])

        # we now have a final answer for the redshift of the cluster.
        # if the user wants, plot it up
        if params["final_CMD"] == "1":
            # set up the plot
            fig, ax = plt.subplots(figsize=(9, 6))
            ax = plotting.cmd(self, ax, cfg)
            plotting.add_vega_labels(ax, cfg)
            plotting.add_one_model(ax, self.models[cfg["color"]]
                                                  [self.z[cfg["color"]].value],
                                  "k")
            # I want to plot both the low and high models, so get those zs
            high_z = self.z[cfg["color"]].value + \
                     self.z[cfg["color"]].upper_error
            low_z = self.z[cfg["color"]].value - \
                    self.z[cfg["color"]].lower_error

            plotting.add_one_model(ax, self.models[cfg["color"]][high_z],
                                   "#AAAAAA")
            plotting.add_one_model(ax, self.models[cfg["color"]][low_z],
                                   "#AAAAAA")
            plotting.add_redshift(ax, self.z[cfg["color"]])

            self.figures.append(fig)


            # If the user wants, plot the location of the cluster and RS members.
            if params["location"] == "1":
                fig, ax = plt.subplots(figsize=(9, 8), tight_layout=True)
                ax = plotting.location(self, ax, cfg["color"])
                plotting.add_redshift(ax, self.z[cfg["color"]])
                self.figures.append(fig)

        if params["interactive"] == "1":
            fig, (ax1, ax2) = plt.subplots(ncols=2, figsize=[13, 6],
                                           tight_layout=True)
            ax1 = plotting.cmd(self, ax1, cfg)
            plotting.add_vega_labels(ax1, cfg)
            plotting.add_redshift(ax1, self.z[cfg["color"]])
            plotting.add_one_model(ax1, self.models[cfg["color"]][self.z[cfg["color"]].value], "k")
            plotting.add_flags(ax1, self.flags[cfg["color"]])

            ax2 = plotting.location(self, ax2, cfg["color"])
            plotting.add_redshift(ax2, self.z[cfg["color"]])
            plotting.add_flags(ax2, self.flags[cfg["color"]])

            for s_fig in self.figures:
                plt.close(s_fig)

            plt.show(block=False)
            flags = raw_input("Enter the flags for this cluster: [i/f/enter]: ")
            plt.close(fig)

            if flags == "f":
                self.flags[cfg["color"]] += 8

    def _location_cut(self, radius):
        """
        Does a location cut on the galaxies in the image.

        Only those within a certain radius are marked as being near_center,
        which is what we will use for the rest of the fitting. This throws
        away foregrounds, leaving the most dense portion of the cluster. A
        good radius to pick isn't necessarily the radius of the cluster.
        Picking a small radius can increase the signal to noise by only
        including the densest part of the cluster, and throwing out most
        foregrounds.

        The radius cut is done using distance from the overdensity center, if
        that was included in the catalog, or distance from the center of the
        image.

        :param radius: radius of the cut, in arcminutes.
        :return: None, but galaxies near the center are marked as having
                 near_center = True.
        """

        ras = [source.ra for source in self.sources_list]
        decs = [source.dec for source in self.sources_list]

        middle_ra = (max(ras) + min(ras)) / 2.0
        middle_dec = (max(decs) + min(decs)) / 2.0

        for source in self.sources_list:
            if source.dist is None:
                # Use pythagorean theorem to find distance in degrees, then
                # multiply by 3600 to convert to arcsec
                source.dist = np.sqrt((source.ra - middle_ra)**2 +
                                      (source.dec - middle_dec)**2) * 3600

            if source.dist < radius*60.0:  # convert radius to arcsec
                source.near_center = True
            else:
                source.near_center = False

    def _initial_z(self, cfg):
        """
        Find a decent initial redshift estimate, based on the number of
        galaxies near each model.

        It iterates through all redshifts, and counts the number of galaxies
        that are within XXXXXXX color of the model at that redshift. Then the
        redshift that has the highest number of galaxies is the
        redshift selected. It's a quick a dirty estimate.

        :return: an intial redshift estimate
        """

        # Get models with a large spacing, since we don't need a lot of
        # accuracy here.
        models = model.model_dict(0.05)[cfg["color"]]

        # set placeholder values that will be replaced as we go
        max_nearby = -999
        best_z = -999

        z_nearby_pairs = []

        # Iterate through the redshifts
        for z in sorted(models):
            nearby = 0  # reset the number of nearby galaxies

            this_model = models[z]
            mag_point = this_model.mag_point
            for source in self.sources_list:
                if source.near_center:
                    source_mag = source.mags[cfg["red_band"]].value
                    source_color = source.colors[cfg["color"]].value
                    # get the expected RS color for a galaxy of this magnitude
                    rs_color = this_model.rs_color(source.mags[cfg["red_band"]].value)

                    # then determine the limits for a valid RS galaxy
                    bright_mag = mag_point - cfg["initial_mag"][0]
                    faint_mag = mag_point + cfg["initial_mag"][1]
                    blue_color = rs_color - cfg["initial_color"][0]
                    red_color = rs_color + cfg["initial_color"][1]
                    # see if it passes a color and magnitude cut
                    if (bright_mag < source_mag < faint_mag) and \
                       (blue_color < source_color < red_color):
                        # if it did pass, note that it is nearby
                        nearby += 1

            z_nearby_pairs.append((z, nearby))
            # replace the best values if this is the best
            if nearby > max_nearby:
                max_nearby = nearby
                best_z = z

        redshifts, nearbies = zip(*z_nearby_pairs)

        # check for the double red sequence
        self._double_red_sequence(nearbies, cfg["color"])

        # Turn this into a data object, with errors that span the maximum
        # range, since we don't have a good feeling yet
        up_error = sorted(models.keys())[-1] - best_z
        low_error = best_z - sorted(models.keys())[0]
        z = data.AsymmetricData(best_z, up_error, low_error)
        return z

    def _double_red_sequence(self, nearby, color):
        """Checks for the possiblity of a double red sequence.

        Is to be used inside the initial_z funciton, since it uses the list of
        nearby galaxies as a function of redshift. It looks for two or more
        maxima in the number of red sequence galaxies simply by comparing each
        point to its neighbors.

        :param nearby: list of galaxies nearby to the red sequence at a given
                       redshift. Should be sorted in order of increasing
                       redshift. This is taken care of by the initial_z
                       function, though, so as long as it is used there
                       everything will be fine.
        :returns: None, but does set the cluster's flag variable if need be.
        """
        num_local_maxima = 0
        # We will compare each one to its 3 neighbors, so start as the third
        # index.
        idx = 3
        # we can't go past the 4th to last item.
        while 3 <= idx <= len(nearby) - 4:
            item = nearby[idx]
            # compare it to its three neighbors on each side.
            if item > nearby[idx-3] and item > nearby[idx-2] and \
               item >= nearby[idx-1] and item >= nearby[idx+1] and \
               item > nearby[idx+2] and item > nearby[idx+3]:
                # if it is bigger than all 6 neighbors, call it a maxima.
                num_local_maxima += 1
                # move 3 ahead, to avoid the possibility of two maxima being
                # right next to each other, which can happen if the top is
                # flat. That obviously isn't what we are looking for here.
                idx += 3
            else:
                idx += 1
        # If there are 2 or more maxima, increment the flag.
        if num_local_maxima >= 2:
            self.flags[color] += 2

    def _set_rs_membership(self, redshift, bluer, redder,
                           brighter, dimmer, cfg):
        """Set some sources to be RS members, based on color and mag cuts.

        :param redshift: redshift of the red sequence that these sources
                         will be identified as belonging to.
        :param bluer: maximum color difference on the blue side from the
                      characteristic color of the red sequence at the
                      magnitude of the galaxy.
        :param redder: maximum color differenece on the red side from the
                       characteristic color of the RS
        :param brighter: maximum magnitude difference (on the bright end)
                         from the characteristic magnitude of the red
                         sequence.
        :param dimmer: maximum magnitude difference (on the faint end)
                         from the characteristic magnitude of the red
                         sequence.

        As an example: At some redshift, the red sequence has a characteristic
        magnitude of 20, and a characteristic color of zero. We pass in
        bluer=0.1, redder=0.2, brighter=2.0, dimmer=1.0. Any galaxies that
        have magnitude 18 to 21 pass the magnitude cut. The color cut is
        trickier, since the RS has some slope. We find the characteristic
        color of the red sequence at the ch2 magnitude of the galaxy (say
        0.05 for a particular galaxy). Then if the color is within the
        bounds set by bluer and redder (in this case -0.05 to 0.25), then it
        passes the color cut. If a galaxy passes both the magnitude and
        color cuts, it is marked as a red sequence galaxy.

        Note: This function marks galaxies both inside and outside the
        location cut as RS members. This is because the loctaion cut may be
        smaller than the cluster (in fact this is often good to do), and we
        don't want to mark galaxies as not RS members just because they are
        outside the (possibly) small location cut.

        :return: None, but galaxies that are RS members are marked as such.
        """

        # get the model, it's characteristic magnitude, and then turn it
        # into magnitude limits bsed on the parameters passed in

        rs_model = self.models[cfg["color"]][redshift]
        char_mag = rs_model.mag_point
        dim_mag = char_mag + dimmer
        bright_mag = char_mag - brighter

        for source in self.sources_list:
            # get the color correspoinding to the red sequence at the ch2
            # magnitude of this particular source
            char_color = rs_model.rs_color(source.mags[cfg["red_band"]].value)
            # turn it into color limits based on parameters passed in
            red_color = char_color + redder
            blue_color = char_color - bluer
            # a function in the source class does the actual marking
            source.rs_membership(blue_color, red_color, bright_mag, dim_mag,
                                 cfg["color"], cfg["red_band"])

    def _chi_square_w_error(self, cfg):
        """Does chi-squared fitting, and returns the best fit value and the
        1 sigma error.

        The best fit value is simply the value that minimizes the reduced
        chi squared value. The upper and lower errors on this are the value
        at which the chi squared value is 1 greater than the best fit.

        :returns: An AsymmetricData object, where value is the best fit
        values, and upper and lower values are indicated.
        """

        # we only want to do the fitting on those near the center, and those
        #  that are in our tentative RS.
        to_fit = [source for source in self.sources_list
                  if source.RS_member[cfg["color"]] and source.near_center]

        # if there isn't anything to fit to, keep the initial z
        if len(to_fit) == 0:
            return self.z

        # initialize lists for the chi squared distribution and the redshifts
        chi_sq_values = []
        redshifts = []

        # test each model
        for z in sorted(self.models[cfg["color"]]):
            chi_sq = 0  # reset the chi squared value for this model
            this_model = self.models[cfg["color"]][z]
            for source in to_fit:
                # get the model points, then compare that with the data
                model_color = this_model.rs_color(source.mags[cfg["red_band"]].value)
                color = source.colors[cfg["color"]].value
                error = source.colors[cfg["color"]].error
                chi_sq += ((model_color - color)/error)**2

            # reduce the chi square values
            chi_sq /= len(to_fit)
            # put these values into the lists, so we can keep track of them
            chi_sq_values.append(chi_sq)
            redshifts.append(z)

        # get the minimum chi squared value, and it's index in the list.
        best_chi = min(chi_sq_values)
        best_chi_index = chi_sq_values.index(best_chi)

        # Start finding errors, using the chi squared distribution. Where it's
        # one greater than the best chi, that's where the error is.
        high_idx = best_chi_index
        # find the place where the chi value is one greater than the best
        while high_idx < len(chi_sq_values) - 1 and \
                chi_sq_values[high_idx] - best_chi < 1.0:
            # Note: len(chi_sq_values) - 1 needs that -1 so that we don't
            # end up with an high_idx that is past the end of chi_sq_values
            high_idx += 1
        # high_idx will now point to the first value where the chi squared
        # value is one greater than the best fit value.

        # do the same thing for the low error
        low_idx = best_chi_index
        while low_idx > 0 and chi_sq_values[low_idx] - best_chi < 1.0:
            low_idx -= 1

        # now get the redshifts corresponding to the best fit, the low
        # error, and the high error
        # This works because the indexing will be the same for redshifts as
        # it was for chi_sq_values
        best_z = redshifts[best_chi_index]
        high_z = redshifts[high_idx]
        low_z = redshifts[low_idx]

        # turn these limits into errors, then into an AsymmetricData object
        high_error = high_z - best_z
        low_error = best_z - low_z
        return data.AsymmetricData(best_z, high_error, low_error)
        # TODO: that was a long function. Break it up somehow?

    def _clean_rs_check(self, cfg):
        """ Determine whether or not there is a clean red sequence.

        This works by counting the number of red sequence galaxies of the best
        fit model, then comparing that to the number of red sequence galaxies
        if the red sequence were bluer or redder. If the best fit doesn't have
        a lot more than the non-best fits, then we mark the flag for a
        not clean red sequence.

        :return: None, but the flag is incremented if there isn't a clean red
                 sequence.
        """

        # set cuts to be used each time
        bluer = cfg["bluer_color_cut"][-1]
        redder = cfg["redder_color_cut"][-1]
        brighter = cfg["brighter_mag_cut"]
        dimmer = cfg["dimmer_mag_cut"]
        # set the red sequence members for the accepted red sequence.
        self._set_rs_membership(self.z[cfg["color"]].value,
                                bluer=bluer, redder=redder,
                                brighter=brighter, dimmer=dimmer,
                                cfg=cfg)
        # count the RS members in the best fit
        best_rs = self._count_galaxies(cfg["color"])

        # set red sequence members to be in the color range 0.3 redder than
        # the best fit. It's weird that we subtract from bluer and add to
        # redder, but if you think of making it less blue and more red you can
        # convince yourself.
        self._set_rs_membership(self.z[cfg["color"]].value,
                                bluer=bluer - 0.3, redder=redder + 0.3,
                                brighter=brighter, dimmer=dimmer,
                                cfg=cfg)
        # again count the galaxies in this red sequence
        red_rs = self._count_galaxies(cfg["color"])

        # set red sequenc members to be a bluer red sequence
        self._set_rs_membership(self.z[cfg["color"]].value,
                                bluer=bluer + 0.3, redder=redder - 0.3,
                                brighter=brighter, dimmer=dimmer,
                                cfg=cfg)
        blue_rs = self._count_galaxies(cfg["color"])

        # Compare the numbers in the 3 red sequences. Set the flag if the
        # number of galaxies in the best red sequence is less than twice
        # the sum of the two offset red sequences. The 2 times is arbitrary.
        # It was chosen to make things I thought looked bad have this flag.
        if ((red_rs + blue_rs) * 2.0) >= best_rs:
            self.flags[cfg["color"]] += 4

    def _count_galaxies(self, color):
        """ Counts the number of red sequence galaxies near the center.

        :return: number of red sequence galaxies that are near the center.
        :rtype: float. I return float so that it can be used in division in
                Python 2.7 smartly.
        """
        count = 0
        for source in self.sources_list:
            if source.near_center and source.RS_member[color]:
                count += 1
        return float(count)

    def _location_check(self, color):
        """Looks to see if the red sequence galaxies are concentrated in the
        middle. If they are not, this will raise a flag.

        It works be getting the percent of galaxies within the location cut
        that are red sequence members, then comparing that to the percentage
        outside the location cut. If the percentage inside isn't 75 percent
        higher, then the flag is raised.

        """
        # find how many objects are near then center and not near the center
        # that are or are not red sequence members. I converted everything
        # to floats to avoid the rounding that comes from dividing integers
        # in Python 2.x
        total_near_center = float(len([source for source in self.sources_list
                                       if source.near_center]))
        rs_near_center = float(len([source for source in self.sources_list
                                    if source.near_center and
                                    source.RS_member[color]]))

        total_not_near_center = float(len([source for source in
                                           self.sources_list if
                                           not source.near_center]))
        rs_not_near_center = float(len([source for source in self.sources_list
                                        if not source.near_center and
                                        source.RS_member[color]]))

        # Calculate the percent of sources that are red sequence members both
        # near and far from the center.
        try:
            near_rs_percent = rs_near_center / total_near_center
            not_near_rs_percent = rs_not_near_center / total_not_near_center

            # raise the flag if the percent near the center isn't high enough.
            if near_rs_percent <= not_near_rs_percent * 1.75:
                self.flags[color] += 1
        except ZeroDivisionError:
            self.flags[color] += 1

    def rs_catalog(self, params, cfg):
        """ Writes a catalog of all the objects, indicating the RS members.

        :returns: none, but the catalog is saved to disk.
        """

        filepath = params["rs_catalog_dir"] + self.name + ".rs.cat"

        with open(filepath, "w") as cat:
            # I want the headers to line up over the data
            header = "# {:12s} {:12s} {:10s} {:10s} {:10s} {:10s} {:10s} " \
                     "{:10s} {:6s} {:2s}\n".format("ra", "dec", "ch1", "ech1",
                                             "ch2", "ech2", "ch1-ch2",
                                             "ech1-ch2", "center", "RS")
            cat.write(header)

            for source in self.sources_list:
                if source.RS_member[cfg["color"]]:
                    rs = 1
                else:
                    rs = 0

                if source.near_center:
                    center = 1
                else:
                    center = 0

                if params["mags"] == "vega":
                    # convert output to Vega mags
                    out_ch1 = source.ch1.value - 2.787
                    out_ch2  = source.ch2.value - 3.260
                    out_ch1_m_ch2 = source.ch1_m_ch2.value - 2.787 + 3.260
                else:  # leave output mags in AB
                    out_ch1 = source.ch1.value
                    out_ch2 = source.ch2.value
                    out_ch1_m_ch2 = source.ch1_m_ch2.value
                out_ch1_err = source.ch1.error
                out_ch2_err = source.ch2.error
                out_ch1_m_ch2_err = source.ch1_m_ch2.error

                def fix_data(data_imem):
                    if abs(data_imem) > 50:
                        return -99
                    else:
                        return data_imem

                out_ch1 = fix_data(out_ch1)
                out_ch2 = fix_data(out_ch2)
                out_ch1_m_ch2 = fix_data(out_ch1_m_ch2)
                out_ch1_err = fix_data(out_ch1_err)
                out_ch2_err = fix_data(out_ch2_err)
                out_ch1_m_ch2_err = fix_data(out_ch1_m_ch2_err)

                cat.write("  {:<12.7f} {:<12.7f} {:<10.2f} {:<10.3f} {:<10.2f} {:<10.3f} {:<10.2f} "
                          "{:<10.3f} {:<6d} {:<2d}\n".format(source.ra,
                                                  source.dec,
                                                  out_ch1,
                                                  out_ch1_err,
                                                  out_ch2,
                                                  out_ch2_err,
                                                  out_ch1_m_ch2,
                                                  out_ch1_m_ch2_err,
                                                  center, rs))


def save_as_one_pdf(figs, filename):
    """
    Save the figures into one long PDF file

    :param figs: list of figures to be saved as PDFs
    :param filename: place where the PDFs will be saved
    :return: none
    """

    # check if there are actually figures to save.
    if len(figs) == 0:
        return

    # if so, save them.
    pp = PdfPages(filename)
    for fig in figs:
        pp.savefig(fig)
    pp.close()
    for fig in figs:
        plt.close(fig)
